import sys, sim_fixed as sp
from sim_fixed import run, show, Ship
FIX = dict(FixRudder=True, FixTilt=True, BoostStartFuelCost=10., BoostKickCooldown=1.5, BrakeUseAFan=True, DriftKeepThrottle=True, DriftBrakeScale=0.0)
def mk(fix): return Ship(dict(FIX) if fix else {})
for fix in (False, True):
    print("=================== FIX" if fix else "=================== CODED")
    for dt in (1/30, 1/120):
        print(f"--- dt {dt:.4f}")
        s, rows = run(lambda t, s: {'thr': 1.0}, dt, 30, ship=mk(fix), every=1)
        vss = rows[-1][1]['vf']; t80 = next(t for t, te, lg in rows if te['vf'] >= 0.8*vss)
        print(f" top {vss:.1f} m/s 0->80% {t80}s")
        def brake_script(t, s): return {'thr': 1.0} if t < 30 else {'brake': True}
        s, rows = run(brake_script, dt, 40, ship=mk(fix), every=0.05)
        t_stop = next((t for t, te, lg in rows if t > 30 and te['vf'] <= 1.0), None)
        print(f" brake vf<1 after {t_stop-30 if t_stop else None:.2f} s; max |pitch| {max(abs(te['pitch']) for t,te,lg in rows if t>30):.1f}")
        def turn(t, s): return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0}
        s, rows = run(turn, dt, 38, ship=mk(fix), every=1)
        print(" top-speed full steer:"); show([r for r in rows if r[0] in (31, 32, 34, 38)], keys=('speed','vf','vl','yawrate','roll','pitch'))
        def bturn(t, s): return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0, 'boost': True}
        s, rows = run(bturn, dt, 36, ship=mk(fix), every=1)
        print(" boost turn from cruise:"); show([r for r in rows if r[0] in (31, 32, 33, 34, 36)], keys=('speed','vf','vl','yawrate','roll','pitch','fuel'))
        def drift(t, s): return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0, 'brake': True}
        s, rows = run(drift, dt, 34, ship=mk(fix), every=1)
        import math
        print(" drift:"); 
        for t,te,lg in rows:
            if t>=30: print(f"   t={t:.0f} speed={te['speed']:.1f} vf={te['vf']:.1f} slip={math.degrees(math.atan2(te['vl'], max(te['vf'],1e-3))):.0f} yawrate={te['yawrate']:.1f} roll={te['roll']:.1f} pitch={te['pitch']:.1f}")
        s, rows = run(lambda t, s: {'steer': 1.0}, dt, 5, ship=mk(fix), every=1)
        print(" pivot:"); show(rows[-2:], keys=('speed','yawrate','roll','pitch'))
    dt=1/60
    def hold(t, s): return {'thr': 1.0, 'boost': True}
    def tap(t, s):
        k = int(round(t / dt)); return {'thr': 1.0, 'boost': (k % 8) == 0}
    def tap1(t, s):
        k = int(round(t / dt)); return {'thr': 1.0, 'boost': (k % 60) == 0}
    for name, f in (('hold Shift', hold), ('tap 7.5 Hz', tap), ('tap 1 Hz', tap1)):
        s, rows = run(f, dt, 12, ship=mk(fix), every=2)
        print(" "+name); show(rows, keys=('speed', 'vf', 'pitch', 'fuel'))
