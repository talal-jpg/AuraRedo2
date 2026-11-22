import sim_fixed as sp
from sim_fixed import run, show, Ship
FIX = dict(FixRudder=True, FixTilt=True, BoostStartFuelCost=10., BoostKickCooldown=1.5, BrakeUseAFan=True, DriftKeepThrottle=True, DriftBrakeScale=0.0)
for fix in (False, True):
    print("FIX" if fix else "CODED")
    mk = lambda: Ship(dict(FIX) if fix else {})
    dt = 1/60
    s, rows = run(lambda t, s: {}, dt, 10, ship=mk(), every=5); te=rows[-1][1]; print(f" hover z {te['z']:.3f} roll {te['roll']:.3f} pitch {te['pitch']:.3f}")
    def mid(t, s): return {'thr': 0.35} if t < 20 else {'thr': 0.35, 'steer': 1.0}
    s, rows = run(mid, dt, 26, ship=mk(), every=1); print(" mid-speed turn:"); show([r for r in rows if r[0] in (20, 21, 22, 24, 26)], keys=('speed','vf','vl','yawrate','roll','pitch'))
    s, rows = run(lambda t, s: {'strafe': 1.0}, dt, 4, ship=mk(), every=1); print(" strafe:"); show(rows[-1:], keys=('vl','roll','pitch','yawrate'))
    def rev(t, s): return {'thr': -1.0}
    s, rows = run(rev, dt, 10, ship=mk(), every=5); print(" reverse:"); show(rows[-1:], keys=('vf','pitch'))
    def steerleft(t, s): return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': -1.0}
    s, rows = run(steerleft, dt, 34, ship=mk(), every=1); print(" left turn top:"); show([r for r in rows if r[0] in (32, 34)], keys=('vf','vl','yawrate','roll','pitch'))
    def release(t, s): return {'thr': 1.0} if t < 30 else ({'thr': 1.0, 'steer': 1.0} if t < 34 else {'thr': 1.0})
    s, rows = run(release, dt, 38, ship=mk(), every=0.5); print(" turn release:"); show([r for r in rows if r[0] in (34.5, 35, 36, 38)], keys=('vf','vl','yawrate','roll','pitch'))
