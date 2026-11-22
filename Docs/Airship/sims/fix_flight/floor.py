import inspect, math, sim_fixed as sp
from sim_fixed import *
GROUND = 100000.0 - 3000.0
def make(depth, minclear, brake_acc, tracelen=1500.0):
    src = inspect.getsource(sp.Ship.forces)
    src = src.replace("Z = s.actor_loc()[2]", "Z = s.actor_loc()[2]\n        s.trace()")
    src = src.replace("FvWorld = clamp(",
        f"if s.mingd >= 0: VzCmd = max(VzCmd, 1.5*({minclear} - s.mingd))\n"
        f"        if s.mingd >= 0 and {brake_acc} > 0: VzCmd = max(VzCmd, -math.sqrt(2*{brake_acc}*max(s.mingd - {minclear}, 0.0)))\n"
        "        FvWorld = clamp(")
    src = src.replace("fb = mul(PodDir[i], s.podF[i])",
      f"cush = 0.25*W*0.35*(1 - s.gd[i]/{tracelen})**2 if 0 <= s.gd[i] < {tracelen} else 0.0\n            fb = mul(PodDir[i], s.podF[i] + cush)")
    src = "\n".join(l[4:] if l.startswith("    ") else l for l in src.splitlines())
    ns = dict(vars(sp)); ns['math'] = math; exec(src, ns)
    class ShipG(sp.Ship):
        def trace(s):
            s.gd = []
            for p in PODS:
                z = add(s.actor_loc(), qrot(s.q, p))[2]
                h = z - GROUND
                d = h - depth
                s.gd.append(max(d, 0.0) if 0 <= h < tracelen + depth else -1.0)
            v = [g for g in s.gd if g >= 0]
            s.mingd = min(v) if v else -1.0
    ShipG.forces = ns['forces']
    return ShipG
for label, depth, mc, acc in (("coded (pivot, 600)", 0, 600, 0), ("nozzle 470, clear 500, no limiter", 470, 500, 0), ("nozzle 470, clear 500, limiter 0.6g", 470, 500, 588), ("nozzle 470, clear 400, limiter 0.6g", 470, 400, 588)):
    C = make(depth, mc, acc)
    for dt in (1/30, 1/120):
        s = C(); s.gd = [-1]*4; s.mingd = -1
        t = 0; minpod = 1e9; zp=[]
        while t < 12:
            s.step({'lift': -1.0}, dt); t += dt
            zpods = [add(s.actor_loc(), qrot(s.q, p))[2] - GROUND for p in PODS]
            minpod = min(minpod, min(zpods))
        print(f"{label} dt={dt:.4f}: lowest pivot {minpod/100:.2f} m -> nozzle exit {(minpod-470)/100:.2f} m; final pivot {min(zpods)/100:.2f} m")
