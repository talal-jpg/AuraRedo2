# Numbers behind Docs/Airship/controls/BASELINE.md sections 4a-4e. One process, a few seconds:
#   python3 Docs/Airship/controls/sims/baseline_checks.py
# Everything here is the Python port (baseline_sim.py), not PIE. PIE references are printed next to the sim values.
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'sims', 'fix3'))
import baseline_sim as B  # noqa: E402
import cap_model as C     # noqa: E402

BOX = B.INERTIA_BOX
# Chaos keeps the principal moments in its eigen-solver order (largest, smallest, middle) when the hull's tensor is not
# diagonal in hull axes; ApplyForces reads them as if they were the hull X/Y/Z moments (BASELINE 4a). Every run below uses
# the UCX hull inertia (the Ship default); PERM = what GetInertiaTensor() returns for it = v1 as PIE runs.
PERM = B.INERTIA_UCX_CHAOS
BOX_PERM = (BOX[2], BOX[0], BOX[1])


def row(t, rows):
    return B.at(rows, t)


# ------------------------------------------------------------------------------------------------ 0. reproduction
def reproduce():
    print('== 0. v1 reproduction (sim, 30 Hz) against PIE (pie_validate run 2 / pie_smoke) ==')
    PIE_PITCH = [-2.7, -9.0, -14.5, -16.3, -13.0, -6.3, -0.65, 1.6, 1.2]
    print('PIE   throttle from rest: v 9.4 22.3 34.7 44.2 48.8 at 1-5 s, pitch %s (min -16.5)' % PIE_PITCH)
    for name, I, ci in (('sim UCX inertia, Chaos order (v1 as PIE)', B.INERTIA_UCX, PERM), ('sim UCX inertia, fixed (code intent)', B.INERTIA_UCX, None),
                        ('sim box estimate, Chaos order', BOX, BOX_PERM)):
        s, rows = B.run(lambda t, s: {'thr': 1.0}, 9.5, inertia=I, code_inertia=ci)
        print('%-48s v %s pitch %s (min %.1f)' % (name, ' '.join('%4.1f' % row(k, rows)['vf'] for k in range(1, 6)),
              [round(row(k, rows)['pitch'], 1) for k in range(1, 10)], min(x['pitch'] for x in rows)))
    print('PIE   boost (started at the end of the full-steer turn, steer 0.8): pitch -8.0 -14.0 -17.5 at 1-3 s; turn at top: 35.2 deg/s, roll 16.5..17.9, pitch about -7..-2.8')
    for name, ci in (('sim UCX, Chaos order (v1 as PIE)', PERM), ('sim UCX, fixed', None)):
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'boost': True}, 16, code_inertia=ci)
        bp = [round(row(12 + k, rows)['pitch'], 1) for k in (1, 2, 3)]
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else ({'thr': 1.0, 'steer': 1.0} if t < 20 else {'thr': 1.0, 'steer': 0.8, 'boost': True}), 24, code_inertia=ci)
        bt = [round(row(20 + k, rows)['pitch'], 1) for k in (1, 2, 3)]
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'steer': 1.0}, 20, code_inertia=ci)
        r = [x for x in rows if x['t'] > 14]
        print('%-48s boost pitch %s (from a turn, as PIE: %s) | turn %.1f deg/s, roll %.1f..%.1f, pitch %.1f..%.1f' % (
            name, bp, bt, sum(x['yawrate'] for x in r) / len(r), min(x['roll'] for x in r), max(x['roll'] for x in r),
            min(x['pitch'] for x in r), max(x['pitch'] for x in r)))
    s, rows = B.run(lambda t, s: {'lift': 1.0} if t < 4 else ({'lift': -1.0} if t < 8 else {}), 11, code_inertia=PERM)
    print('PIE   lift +1 4 s, -1 4 s, release: vz -6.46 at ~1.0 s and -0.46 at ~2.0 s after release')
    print('sim   same sequence:                vz %.2f at 1.0 s and %.2f at 2.0 s after release' % (row(9, rows)['vz'], row(10, rows)['vz']))
    print()


# ------------------------------------------------------------------------------------------------ 4a. nose dip
def nose_dip():
    print('== 4a. nose dip: throttle / boost / brake / turn (sim) ==')
    cases = [
        ('v1 (Chaos order, as PIE)', {}, PERM),
        ('fix 1: inertia in hull axes', {}, None),
        ('fix 1 + 2: + fan torque feed-forward', {'bFanTorqueFeedForward': True}, None),
        ('fix 1 + 2 + 3: + targets 4 / -4 / 1.5', {'bFanTorqueFeedForward': True, 'PitchPerG': 4., 'PitchMinDeg': -4., 'BoostPitchDeg': 1.5}, None),
        ('fix 1 + 2 + 3b: + targets 3 / -3 / 1, flare 3', {'bFanTorqueFeedForward': True, 'PitchPerG': 3., 'PitchMinDeg': -3., 'BoostPitchDeg': 1., 'PitchMaxDeg': 3.}, None),
        ('params only, bug kept: FF + targets 4 / -4 / 1.5', {'bFanTorqueFeedForward': True, 'PitchPerG': 4., 'PitchMinDeg': -4., 'BoostPitchDeg': 1.5}, PERM),
    ]
    print('%-50s | thr pitch min | v at 3 s | boost pitch min | brake flare max, reverse | turn pitch' % 'case')
    for name, p, ci in cases:
        s, rows = B.run(lambda t, s: {'thr': 1.0}, 9.5, params=p, code_inertia=ci)
        tmin, v3 = min(x['pitch'] for x in rows), row(3, rows)['vf']
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'boost': True}, 16, params=p, code_inertia=ci)
        bmin = min(x['pitch'] for x in rows if x['t'] > 12)
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'brake': True}, 18, params=p, code_inertia=ci)
        r = [x for x in rows if x['t'] > 12]
        fmax, vrev = max(x['pitch'] for x in r), min(x['vf'] for x in r)
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'steer': 1.0}, 20, params=p, code_inertia=ci)
        r = [x for x in rows if x['t'] > 14]
        print('%-50s | %6.1f | %5.1f | %6.1f | %5.1f %5.2f | %5.1f..%4.1f' % (name, tmin, v3, bmin, fmax, vrev,
              min(x['pitch'] for x in r), max(x['pitch'] for x in r)))
    print()


# ------------------------------------------------------------------------------------------------ 4b / 4c. vertical
def release(p, lift):
    s, rows = B.run(lambda t, s: {'lift': lift} if t < 4 else {}, 9, params=p, code_inertia=PERM)
    r = [x for x in rows if x['t'] > 4]
    vz = [row(4 + k, rows)['vz'] for k in (0.5, 1.0, 1.5, 2.0)]
    settle = next((x['t'] - 4 for x in r if all(abs(y['vz']) < 0.5 for y in r if y['t'] >= x['t'])), None)
    ext = max(x['z'] for x in r) if lift > 0 else min(x['z'] for x in r)
    over = abs(ext - r[-1]['z'])
    return vz, settle, r[-1]['z'] - r[0]['z'], over


def brake_mid_climb(p):
    def sc(t, s):
        if abs(t - 1.0) < 0.017:
            s.v = (s.v[0], s.v[1], 480.0)  # moving up 4.8 m/s in hold mode (val f2: impact + floor), then brake
        return {'brake': t > 1.1}
    s, rows = B.run(sc, 8, params=p, code_inertia=PERM)
    r = [x for x in rows if x['t'] > 1.1]
    top = max(x['z'] for x in r)
    return top - r[0]['z'], top - r[-1]['z']


def vertical():
    print('== 4b / 4c. vertical: release from full climb (+12) / full descent (-15), brake press while rising 4.8 m/s (sim) ==')
    V = {'LiftTauRelease': 0.08, 'HoldBrakeAccel': 1176., 'VertBrakeAccel': 490., 'bBrakeHoldLead': True}
    cases = [
        ('v1', {}),
        ('LiftTauRelease 0.08 alone (worse)', {'LiftTauRelease': 0.08}),
        ('bBrakeHoldLead alone', {'bBrakeHoldLead': True}),
        ('Collective 0..2.2, PodForceMax 0.65', {'CollectiveMin': 0.0, 'CollectiveMax': 2.2, 'PodForceMax': 0.65}),
        ('vertical set (VB 0.5 g, sqrt 1.2 g, rel 0.08, lead)', V),
        ('vertical set, VB 0.8 g, sqrt 1.5 g', dict(V, VertBrakeAccel=784., HoldBrakeAccel=1470.)),
    ]
    print('%-52s | climb: vz at +0.5/1/1.5/2 s, settled s, metres after release, bob | descent: same | brake: rise, comes back' % 'case')
    for name, p in cases:
        a, b, c = release(p, 1.0), release(p, -1.0), brake_mid_climb(p)
        f = lambda v: ' '.join('%5.1f' % x for x in v)
        print('%-52s | %s %4s %5.1f %4.2f | %s %4s %5.1f %4.2f | %4.2f %4.2f' % (
            name, f(a[0]), a[1] and '%.2f' % a[1], a[2], a[3], f(b[0]), b[1] and '%.2f' % b[1], b[2], b[3], c[0], c[1]))
    for n, p in (('v1', {}), ('vertical set', V)):
        s, rows = B.run(lambda t, s: {'lift': 1.0} if 1 < t < 1.3 else {}, 6, params=p, code_inertia=PERM)
        print('lift tap 0.3 s, %-12s: net climb %.2f m' % (n, rows[-1]['z'] - rows[0]['z']))
    print()


# ------------------------------------------------------------------------------------------------ 4c. brake, 4d. drift
def brake_and_drift():
    print('== 4c. brake from top speed (sim, Chaos order) ==')
    for name, p in (('v1', {}), ('BrakeFadeSpeed 1000', {'BrakeFadeSpeed': 1000.}), ('BrakeFadeSpeed 1000 + Kbrake 0.6', {'BrakeFadeSpeed': 1000., 'Kbrake': 0.6})):
        s, rows = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {'thr': 1.0, 'brake': True}, 18, params=p, code_inertia=PERM)
        r = [x for x in rows if x['t'] > 12]
        v0 = r[0]['vf']
        half = next(x['t'] - 12 for x in r if x['vf'] <= v0 / 2)
        peak = max(-(r[i + 1]['vf'] - r[i]['vf']) * 30.0 for i in range(len(r) - 1)) / 9.8
        print('%-34s from %.1f m/s: half speed %.2f s, peak %.1f g, reverses to %.2f m/s, stops in %.1f m' % (
            name, v0, half, peak, min(x['vf'] for x in r), max(x['x'] for x in r) - r[0]['x']))
    print('== 4d. 0.3 m/s forward nudge at hover, drift after 10 s (sim) ==')
    for name, p in (('v1', {}), ('StationKeepGain 1.0', {'StationKeepGain': 1.0}), ('StationKeepGain 2.0', {'StationKeepGain': 2.0})):
        def sc(t, s):
            if abs(t - 0.5) < 0.017:
                s.v = (30.0, s.v[1], s.v[2])
            return {}
        s, rows = B.run(sc, 10.5, params=p, code_inertia=PERM)
        s2, rows2 = B.run(lambda t, s: {'thr': 1.0} if t < 12 else {}, 25, params=p, code_inertia=PERM)
        r2 = [x for x in rows2 if x['t'] > 12]
        half = next(x['t'] - 12 for x in r2 if x['vf'] <= r2[0]['vf'] / 2)
        print('%-22s drift %.2f m; coast from top speed: half speed after %.1f s' % (name, rows[-1]['x'] - rows[0]['x'], half))
    print()


# ------------------------------------------------------------------------------------------------ 4e. impact cap
class UpFree(C.New):
    """cap_model.New with a separate free upward allowance AccelUp (cm/s^2)."""
    def hit(self, now, dt, pre_v, pre_w, v, w, dead=False, kick=(0, 0, 0)):
        p = self.p
        up = p.get('AccelUp', p['Accel'])
        step = min(dt, p['MaxStep'])
        if now - self.last > max(p['Gap'], 2.5 * dt):
            self.used = [0.0] * 4
        else:
            refill = (now - self.last) / max(p['Refill'], 0.01)
            self.used = [max(0.0, u - refill) for u in self.used]
        self.last = now
        free, free_up = p['Accel'] * step, (0.0 if dead else up * step)
        pv = C.add(pre_v, kick)
        v = list(v)
        base = max(pv[2], 0.0)
        g = v[2] - base
        a, self.used[0] = C.spend(g, free_up, p['Rebound'], self.used[0])
        if a < g - 0.01:
            v[2] = base + a
        base, h = C.size2(pv), C.size2(v)
        a, self.used[1] = C.spend(h - base, free, p['Gain'], self.used[1])
        if a < h - base - 0.01 and h > 1e-4:
            k = (base + a) / h
            v[0] *= k
            v[1] *= k
        base, sp = C.size(pv), C.size(v)
        a, self.used[2] = C.spend(sp - base, free, p['Gain'], self.used[2])
        if a < sp - base - 0.01 and sp > 1e-4:
            v = C.scl(v, (base + a) / sp)
        return v, w


def impact_cap():
    print('== 4e. impact cap (Docs/Airship/sims/fix3/cap_model.py + a separate upward allowance) ==')
    DT, Z = 1.0 / 30.0, (0, 0, 0)
    for name, kw in (('v1 (Accel 2500, Rebound 250)', {}), ('Rebound 120', {'Rebound': 120.}),
                     ('AccelUp 1300', {'AccelUp': 1300.}), ('AccelUp 1300 + Rebound 120', {'AccelUp': 1300., 'Rebound': 120.})):
        m = UpFree(**kw)
        o1 = m.hit(DT, DT, (8600, 0, 0), Z, (8300, 0, 2600), Z)
        o2 = m.hit(2 * DT, DT, o1[0], Z, (o1[0][0], 0, o1[0][2] + 800), Z)
        res = []
        for acc in (490.0, 1225.0):
            m = UpFree(**kw)
            t = 0.0
            for _ in range(60):
                t += DT
                m.hit(t, DT, (0, 0, 0), Z, (0, 0, 0), Z)
            v = [0.0, 0, 0]
            for _ in range(9):
                t += DT
                v = list(m.hit(t, DT, v, Z, (0, 0, v[2] + acc * DT), Z)[0])
            res.append(v[2] / 100)
        print('%-30s clip +26 m/s up -> %.2f m/s (one step), %.2f (two push steps) | take-off 0.5 g / 1.25 g after 0.3 s: %.2f / %.2f (want 1.47 / 3.68)' % (
            name, o1[0][2] / 100, o2[0][2] / 100, res[0], res[1]))
    print()


if __name__ == '__main__':
    reproduce()
    nose_dip()
    vertical()
    brake_and_drift()
    impact_cap()
