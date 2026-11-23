import math, sim_fixed as sp
from sim_fixed import run, Ship
FIX = dict(FixRudder=True, FixTilt=True, BoostStartFuelCost=10., BoostKickCooldown=1.5, BrakeUseAFan=True, DriftKeepThrottle=True, DriftBrakeScale=0.0)
def turn(t, s): return {'thr': 1.0} if t < 30 else {'thr': 1.0, 'steer': 1.0}
for k in (4.0,):
    for G in (2.5, 2.2, 2.0):
     for eta in (0.35,):
        p = dict(FIX); p['GripALatMaxG'] = G; p['GripEta'] = eta
        s, rows = run(turn, 1/60, 38, ship=Ship(p), every=1)
        sl = {t: math.degrees(math.atan2(-te['vl'], te['vf'])) for t, te, lg in rows}
        sp_ = {t: te['speed'] for t, te, lg in rows}
        yr = {t: te['yawrate'] for t, te, lg in rows}
        print(f"ALatMax {G} eta {eta}: slip 1/2/4/8 s = {sl[31]:.0f}/{sl[32]:.0f}/{sl[34]:.0f}/{sl[38]:.0f}  speed {sp_[32]:.1f}/{sp_[38]:.1f} yaw {yr[34]:.1f} roll {rows[-1][1]['roll']:.1f} pitch {rows[-1][1]['pitch']:.1f}")
