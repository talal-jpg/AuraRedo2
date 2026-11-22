"""Offline port of AAirshipPawn::LimitImpactResponse (fix round 3, kick budgets) + the round-2 episode model, for
scenario checks. Units cm/s, rad/s. Mirrors the C++ line by line."""
import math

DEFAULTS = dict(Rebound=250.0, Gain=500.0, Spin=math.radians(20.0), DeadSpin=math.radians(40.0), Gap=0.25, Refill=1.0,
                Accel=2500.0, SpinAccel=math.radians(90.0), MaxStep=1.0 / 30.0)


def size(v): return math.sqrt(sum(x * x for x in v))
def size2(v): return math.hypot(v[0], v[1])
def sub(a, b): return [x - y for x, y in zip(a, b)]
def add(a, b): return [x + y for x, y in zip(a, b)]
def scl(a, s): return [x * s for x in a]
def dot(a, b): return sum(x * y for x, y in zip(a, b))


def spin_gain(ref, w):
    kick = sub(w, ref)
    rs = size(ref)
    if rs <= 1e-4:
        return kick
    d = scl(ref, 1.0 / rs)
    slowing = min(max(-dot(kick, d), 0.0), rs)
    return add(kick, scl(d, slowing))


def spend(gain, free, cap, used):
    if gain <= free:
        return gain, used
    spent = min(gain - free, max(0.0, cap * (1.0 - used)))
    if cap > 1e-4:
        used = min(1.0, used + spent / cap)
    return free + spent, used


class New(object):
    """Round 3: per-step gains vs the step's own start; Free per step; budgets per contact, refilled."""
    def __init__(self, **kw):
        self.p = dict(DEFAULTS, **kw)
        self.last = -1000.0
        self.used = [0.0, 0.0, 0.0, 0.0]

    def hit(self, now, dt, pre_v, pre_w, v, w, dead=False, kick=(0, 0, 0)):
        p = self.p
        step = min(dt, p['MaxStep'])
        if now - self.last > max(p['Gap'], 2.5 * dt):
            self.used = [0.0] * 4
        else:
            refill = (now - self.last) / max(p['Refill'], 0.01)
            self.used = [max(0.0, u - refill) for u in self.used]
        self.last = now
        free = p['Accel'] * step
        free_up = 0.0 if dead else free
        free_spin = p['SpinAccel'] * step
        pv = add(pre_v, kick)
        v = list(v)
        tol = 0.01
        base = max(pv[2], 0.0)
        g = v[2] - base
        a, self.used[0] = spend(g, free_up, p['Rebound'], self.used[0])
        if a < g - tol:
            v[2] = base + a
        base = size2(pv); h = size2(v); g = h - base
        a, self.used[1] = spend(g, free, p['Gain'], self.used[1])
        if a < g - tol and h > 1e-4:
            s = (base + a) / h; v[0] *= s; v[1] *= s
        base = size(pv); sp = size(v); g = sp - base
        a, self.used[2] = spend(g, free, p['Gain'], self.used[2])
        if a < g - tol and sp > 1e-4:
            v = scl(v, (base + a) / sp)
        gv = spin_gain(pre_w, w); gs = size(gv)
        a, self.used[3] = spend(gs, free_spin, p['DeadSpin'] if dead else p['Spin'], self.used[3])
        w = list(w)
        if a < gs - math.radians(tol) and gs > 1e-4:
            w = sub(w, scl(gv, 1.0 - a / gs))
        return v, w


class Old(object):
    """Round 2 (as reviewed): episode reference frozen at the first hit, allowance Accel x (now - start)."""
    def __init__(self, **kw):
        self.p = dict(DEFAULTS, **kw)
        self.start = self.last = -1000.0
        self.rv = [0, 0, 0]; self.rw = [0, 0, 0]

    def hit(self, now, dt, pre_v, pre_w, v, w, dead=False, kick=(0, 0, 0)):
        p = self.p
        if now - self.last > p['Gap']:
            self.start = now; self.rv = list(pre_v); self.rw = list(pre_w)
        self.last = now
        el = max(0.0, now - self.start); al = p['Accel'] * el
        v = list(v)
        mu = max(self.rv[2], 0.0) + p['Rebound'] + al
        if v[2] > mu: v[2] = mu
        mh = size2(self.rv) + p['Gain'] + al; h = size2(v)
        if h > mh: v[0] *= mh / h; v[1] *= mh / h
        ms = size(self.rv) + p['Gain'] + al
        if size(v) > ms: v = scl(v, ms / size(v))
        k = sub(w, self.rw); mk = (p['DeadSpin'] if dead else p['Spin']) + p['SpinAccel'] * el
        w = list(w)
        if size(w) > size(self.rw) and size(k) > mk:
            w = add(self.rw, scl(k, mk / size(k)))
        return v, w
