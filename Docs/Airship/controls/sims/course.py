"""Gate course (metric M11) and the bot pilots shared by the course and the broadside test (M12).

Course, in metres relative to the start pose (actor origin at (0, 0), heading +X, 30 m above flat ground; z is
relative to the start height). Gates are 40 m wide x 25 m tall, centred on the point, facing their direction:

    G1  straight   (300,   0,   0)  +X      end of a 300 m straight
    S1..S5 slalom  x 450..1050 every 150 m, y +60 / -60 alternating, facing +X
    H1  hairpin    (1230,  80,  0)  +Y      apex of a 180 deg right-hand hairpin, radius ~80 m
    H2  hairpin    (1150, 160,  0)  -X      hairpin exit
    C   climb      (900,  160, +40) -X      40 m up
    D   dive       (650,  160,   0) -X      40 m down again (back at the start height: the course starts 30 m above
                                             the ground, so "-40 m" is read relative to the climb gate)
    F   finish     (400,  160,   0) -X

A gate counts when the actor origin crosses the gate plane inside the frame. Missed gates are skipped (the bot goes
on to the next one). Metrics: completion time (start to crossing the finish plane), gates missed, miss distance
(distance from the gate centre at the crossing, in the gate plane: mean and max over all gates; for a missed gate
also how far outside the frame), steering reversals per minute (sign changes of the raw steer key/axis, |steer| >
0.1), camera-turn reversals per minute (for camera-steered schemes), ground contacts (keel or nozzle exits below
the ground).

Precision measure that is comparable between schemes: the line error, the distance at each gate from the bots'
racing line (the line itself cuts turns up to 15 m inside the gate centre, which the miss distance includes).

Bots: an intent layer (CoursePath: the racing line, fillet arcs that stay inside every gate, a speed profile from
the line's curvature and the scheme's own turn-rate table plus a braking pass; CoursePlanner: course over ground,
speed and altitude from the line with a lag lead, a cross-track correction and a turn-rate feed-forward) and a
per-scheme adapter (Scheme.intent_raw) that turns the intent into that scheme's RAW inputs. Skills: precise (no
delay, analog inputs, the scheme's tuned GAINS) and sloppy human (0.2 s reaction delay, +-15 % gain noise re-drawn
every 0.4-1.2 s from a fixed seed, the scheme's KEY_AXES played as on/off keys with a 0.1 s minimum press or
release).

Run: python3 course.py [scheme] [--latency 0|100] [--skill precise|sloppy]   (about 1.5 s per run)
     python3 course.py [scheme] --tune                                         (bot gains for a scheme, about 1 min)
"""
import math
import random
import sys

from airship_sim import (Sim, Classic, Intent, RawInput, load_scheme, wrap180, clamp, DT, R2D, D2R)

GATE_W = 40.0
GATE_H = 25.0
START_ALT_AGL = 30.0

# name, x, y, z (m, relative to the start pose and height), facing (deg, world yaw the gate is flown through)
GATES = [
    ('G1', 300.0, 0.0, 0.0, 0.0),
    ('S1', 450.0, 60.0, 0.0, 0.0),
    ('S2', 600.0, -60.0, 0.0, 0.0),
    ('S3', 750.0, 60.0, 0.0, 0.0),
    ('S4', 900.0, -60.0, 0.0, 0.0),
    ('S5', 1050.0, 60.0, 0.0, 0.0),
    ('H1', 1230.0, 80.0, 0.0, 90.0),
    ('H2', 1150.0, 160.0, 0.0, 180.0),
    ('C', 900.0, 160.0, 40.0, 180.0),
    ('D', 650.0, 160.0, 0.0, 180.0),
    ('F', 400.0, 160.0, 0.0, 180.0),
]


class Skill:
    def __init__(self, name):
        self.name = name
        if name == 'precise':
            self.reaction, self.noise, self.keyboard = 0.0, 0.0, False
        elif name == 'sloppy':
            self.reaction, self.noise, self.keyboard = 0.2, 0.15, True
        else:
            raise ValueError(name)
        self.min_press = 0.1


class Bot:
    """Perceives the pilot's view of the ship (reaction-delayed for the sloppy skill), asks the planner for an
    Intent, the scheme's adapter for RAW inputs, then applies the skill's keyboard model."""

    KEY_LEVELS = dict(on=0.35, off=0.15)

    def __init__(self, sim, planner, skill, seed=7):
        self.sim = sim
        self.planner = planner
        self.skill = skill
        self.rng = random.Random(seed)
        self.history = []
        self.gain_f = {}
        self.gain_until = {}
        self.keys = {}
        self.prev_raw = RawInput()
        self.planner_gains = None

    def gain(self, ch):
        if self.skill.noise <= 0:
            return 1.0
        t = self.sim.time
        if t >= self.gain_until.get(ch, -1.0):
            self.gain_f[ch] = 1.0 + self.rng.uniform(-self.skill.noise, self.skill.noise)
            self.gain_until[ch] = t + self.rng.uniform(0.4, 1.2)
        return self.gain_f[ch]

    def key(self, ch, v):
        """On/off key with hysteresis and a minimum press / release time."""
        st = self.keys.setdefault(ch, dict(state=0, since=-1e9))
        t = self.sim.time
        want = st['state']
        if st['state'] == 0:
            if v > self.KEY_LEVELS['on']:
                want = 1
            elif v < -self.KEY_LEVELS['on']:
                want = -1
        else:
            if st['state'] * v < self.KEY_LEVELS['off']:
                want = 0
                if st['state'] * v < -self.KEY_LEVELS['on']:
                    want = -st['state']
        if want != st['state'] and t - st['since'] >= self.skill.min_press - 1e-6:
            st['state'], st['since'] = want, t
        return float(st['state'])

    def view(self):
        v = self.sim.pilot_view()
        self.history.append(v)
        if len(self.history) > 120:
            del self.history[0]
        lag = int(round(self.skill.reaction / DT))
        return self.history[max(0, len(self.history) - 1 - lag)]

    def raw(self):
        view = self.view()
        intent = self.planner(self.sim, view)
        scheme = self.sim.scheme
        gains = {k: (v * self.gain(k) if k in scheme.NOISY_GAINS else v) for k, v in scheme.GAINS.items()}
        if self.planner_gains:
            gains.update(self.planner_gains)
        r = scheme.intent_raw(self.sim, intent, view, gains)
        if self.skill.keyboard:
            for ch in getattr(scheme, 'KEY_AXES', ('throttle', 'steer', 'lift', 'strafe')):
                setattr(r, ch, self.key(ch, getattr(r, ch)))
        self.prev_raw = r
        return r


class CoursePath:
    """The racing line: straight legs between the gate centres with a fillet arc at every gate whose apex stays
    GATE_W / 2 - margin from the gate centre (GAINS['margin'], so the line passes inside every frame), sampled every
    2 m with curvature, height (linear along the legs) and a speed limit from the scheme's own turn-rate table
    (v = turn_frac * Rmax(v) * R) plus a braking pass (BRAKE_DECEL)."""

    STEP = 2.0
    BRAKE_DECEL = 8.0       # m/s^2 the speed plan assumes (well inside every scheme's brake)

    def __init__(self, sim, origin_alt_m, start_xy=(0.0, 0.0), v_max=None):
        g = sim.scheme.GAINS
        self.MARGIN = g.get('margin', 7.0)
        self.TURN_FRAC = g.get('turn_frac', 0.85)
        self.alt0 = origin_alt_m
        ox, oy = start_xy
        pts = [(ox, oy, 0.0)] + [(ox + gt[1], oy + gt[2], gt[3]) for gt in GATES]
        last = GATES[-1]
        pts.append((ox + last[1] + 120.0 * math.cos(last[4] * D2R), oy + last[2] + 120.0 * math.sin(last[4] * D2R), last[3]))
        self.corners = pts
        self.samples = []      # (x, y, z_rel, kappa signed (+ = right turn), s)
        self._build(sim, v_max)

    def _build(self, sim, v_max):
        pts = self.corners
        n = len(pts)
        # fillet tangent points for each interior corner
        arcs = {}
        for j in range(1, n - 1):
            a, b, c = pts[j - 1], pts[j], pts[j + 1]
            d1 = (b[0] - a[0], b[1] - a[1])
            d2 = (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            h1, h2 = math.atan2(d1[1], d1[0]), math.atan2(d2[1], d2[0])
            th = wrap180((h2 - h1) * R2D) * D2R
            if abs(th) < 1e-3:
                continue
            r_allow = (GATE_W / 2 - self.MARGIN) / (1.0 / math.cos(abs(th) / 2) - 1.0)
            r = min(r_allow, 0.48 * min(l1, l2) / math.tan(abs(th) / 2))
            arcs[j] = (r, th, h1, h2, l1, l2)
        # walk: legs and arcs
        s = 0.0
        out = []
        for j in range(n - 1):
            a, b = pts[j], pts[j + 1]
            h = math.atan2(b[1] - a[1], b[0] - a[0])
            l = math.hypot(b[0] - a[0], b[1] - a[1])
            cut_in = arcs[j][0] * math.tan(abs(arcs[j][1]) / 2) if j in arcs else 0.0
            cut_out = arcs[j + 1][0] * math.tan(abs(arcs[j + 1][1]) / 2) if (j + 1) in arcs else 0.0
            # straight part of the leg
            seg = max(0.0, l - cut_in - cut_out)
            sx, sy = a[0] + math.cos(h) * cut_in, a[1] + math.sin(h) * cut_in
            k = 0
            while k * self.STEP < seg:
                t = k * self.STEP
                frac = (cut_in + t) / l
                out.append([sx + math.cos(h) * t, sy + math.sin(h) * t, a[2] + (b[2] - a[2]) * frac, 0.0, s])
                s += self.STEP
                k += 1
            # arc at corner j + 1
            if (j + 1) in arcs:
                r, th, h1, h2, l1, l2 = arcs[j + 1]
                sign = 1.0 if th > 0 else -1.0
                ex, ey = b[0] - math.cos(h1) * cut_out, b[1] - math.sin(h1) * cut_out
                cx, cy = ex + r * math.cos(h1 + sign * math.pi / 2), ey + r * math.sin(h1 + sign * math.pi / 2)
                arc_len = r * abs(th)
                m = max(1, int(arc_len / self.STEP))
                for i in range(m):
                    ang = h1 + th * (i / m)
                    px = cx + r * math.cos(ang - sign * math.pi / 2)
                    py = cy + r * math.sin(ang - sign * math.pi / 2)
                    out.append([px, py, b[2], sign / r, s])
                    s += arc_len / m
        self.samples = out
        # speed limit from curvature with the scheme's turn rate, then a braking pass
        vmax = v_max or 60.0
        lim = []
        for p in out:
            kap = abs(p[3])
            if kap < 1e-6:
                lim.append(vmax)
                continue
            v = vmax
            for _ in range(20):
                w = self.TURN_FRAC * sim.rmax_deg(v * 100.0) * D2R
                v = min(vmax, w / kap)
            lim.append(v)
        for i in range(len(lim) - 2, -1, -1):
            lim[i] = min(lim[i], math.sqrt(lim[i + 1] ** 2 + 2 * self.BRAKE_DECEL * self.STEP))
        self.vlim = lim

    def nearest(self, x, y, i0):
        best, bi = 1e18, i0
        for i in range(max(0, i0 - 5), min(len(self.samples), i0 + 80)):
            p = self.samples[i]
            d = (p[0] - x) ** 2 + (p[1] - y) ** 2
            if d < best:
                best, bi = d, i
        return bi


class CoursePlanner:
    """Tracks the racing line: course = the line's heading a lag-time ahead minus a cross-track correction
    (Stanley law, atan(K_CT * e / v)), turn-rate feed-forward from the line's curvature, the speed profile and the
    line's height a little ahead."""

    def __init__(self, sim, origin_alt_m, start_xy=(0.0, 0.0), gains=None):
        g = dict(sim.scheme.GAINS)
        g.update(gains or {})
        self.K_CT = g.get('ct', 0.8)        # 1/s, cross-track gain
        self.LAG = g.get('lag', 0.5)        # s, how far ahead the heading / curvature are read (the ship's yaw lag)
        self.i = 0                  # next gate (the judge moves it)
        self.alt0 = origin_alt_m
        self.ox, self.oy = start_xy
        self.path = CoursePath(sim, origin_alt_m, start_xy)
        self.k = 0
        self.top = 0.97 * sim.top_speed_estimate()

    def gate(self, j):
        name, x, y, z, face = GATES[j]
        return name, (self.ox + x, self.oy + y, self.alt0 + z), face, None

    def heading(self, k):
        s = self.path.samples
        a, b = s[max(0, k - 1)], s[min(len(s) - 1, k + 1)]
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def __call__(self, sim, view):
        loc = [c * 0.01 for c in view['ActorLocCm']]
        path = self.path
        n = len(path.samples)
        self.k = path.nearest(loc[0], loc[1], self.k)
        v = max(view['SpeedMS'], 8.0)
        step = path.STEP
        p = path.samples[self.k]
        h0 = self.heading(self.k)
        e_right = (loc[0] - p[0]) * -math.sin(h0) + (loc[1] - p[1]) * math.cos(h0)
        kl = min(n - 1, self.k + int(v * self.LAG / step))
        h = self.heading(kl)
        course = (h - math.atan2(self.K_CT * e_right, v + 5.0)) * R2D
        ff = path.samples[kl][3] * v * R2D
        ks = min(n - 1, self.k + int(0.8 * v / step))
        speed = min(path.vlim[self.k:ks + 1]) if ks > self.k else path.vlim[self.k]
        kz = min(n - 1, self.k + int(1.5 * v / step))
        alt = self.alt0 + path.samples[kz][2]
        return Intent(course_deg=course, speed=None if speed >= self.top else speed, alt=alt, yaw_rate_ff=ff,
                      brake_hint=view['ForwardSpeedMS'] > speed + 4.0)


class GateJudge:
    """Detects gate plane crossings of the actor origin (interpolated between frames)."""

    def __init__(self, planner):
        self.planner = planner
        self.results = []
        self.prev = None

    def update(self, sim, tele):
        if self.planner.i >= len(GATES):
            return
        loc = tuple(c * 0.01 for c in tele['ActorLocCm'])
        if self.prev is None:
            self.prev = loc
            return
        name, c, face, _ = self.planner.gate(self.planner.i)
        fdir = (math.cos(face * D2R), math.sin(face * D2R))
        s0 = (self.prev[0] - c[0]) * fdir[0] + (self.prev[1] - c[1]) * fdir[1]
        s1 = (loc[0] - c[0]) * fdir[0] + (loc[1] - c[1]) * fdir[1]
        lat_dir = (-fdir[1], fdir[0])
        if s0 < 0.0 <= s1:
            a = -s0 / (s1 - s0) if s1 != s0 else 0.0
            p = tuple(self.prev[k] + (loc[k] - self.prev[k]) * a for k in range(3))
            lat = (p[0] - c[0]) * lat_dir[0] + (p[1] - c[1]) * lat_dir[1]
            vert = p[2] - c[2]
            inside = abs(lat) <= GATE_W / 2 and abs(vert) <= GATE_H / 2
            outside = math.hypot(max(0.0, abs(lat) - GATE_W / 2), max(0.0, abs(vert) - GATE_H / 2))
            line = None
            path = getattr(self.planner, 'path', None)
            if path is not None:
                k = path.nearest(p[0], p[1], getattr(self.planner, 'k', 0))
                q = path.samples[k]
                line = math.hypot(math.hypot(p[0] - q[0], p[1] - q[1]), p[2] - (self.planner.alt0 + q[2]))
            self.results.append(dict(gate=name, t=sim.time, passed=inside, lat=lat, vert=vert,
                                     miss=math.hypot(lat, vert), outside=outside, line=line))
            self.planner.i += 1
        else:
            # gone past it sideways (more than 150 m beyond the plane without crossing it): missed
            if s1 > 150.0:
                self.results.append(dict(gate=name, t=sim.time, passed=False, lat=None, vert=None, miss=None, outside=None,
                                         line=None))
                self.planner.i += 1
        self.prev = loc


def run_course(scheme, skill='precise', latency_ms=0.0, seed=7, timeout=200.0, record=False, gains=None):
    sk = Skill(skill)
    if gains:
        scheme.GAINS = dict(type(scheme).GAINS, **gains)
    sim = Sim(scheme, latency_ms=latency_ms, alt_agl=START_ALT_AGL, seed=seed)
    planner = CoursePlanner(sim, sim.tele()['AltitudeM'])
    judge = GateJudge(planner)
    bot = Bot(sim, planner, sk, seed=seed)
    # settle 2 s (the clock starts at the first input)
    for _ in range(int(2.0 / DT)):
        sim.step(RawInput())
    t0 = sim.time
    steer_sign, steer_rev = 0, 0
    cam_sign, cam_rev, prev_cam = 0, 0, None
    contacts, was_contact = 0, False
    n = 0
    trace = []
    while sim.time - t0 < timeout and planner.i < len(GATES):
        raw = bot.raw()
        rec = sim.step(raw)
        judge.update(sim, rec)
        n += 1
        s = raw.steer
        if abs(s) > 0.1:
            sg = 1 if s > 0 else -1
            if steer_sign and sg != steer_sign:
                steer_rev += 1
            steer_sign = sg
        cy = rec['pilot']['control_yaw']
        if prev_cam is not None and raw.look:
            dcy = wrap180(cy - prev_cam) / DT
            if abs(dcy) > 5.0:
                sg = 1 if dcy > 0 else -1
                if cam_sign and sg != cam_sign:
                    cam_rev += 1
                cam_sign = sg
        prev_cam = cy
        if rec['ground_contact'] and not was_contact:
            contacts += 1
        was_contact = rec['ground_contact']
        if record and n % 3 == 0:
            loc = rec['ActorLocCm']
            trace.append((round(sim.time - t0, 2), round(loc[0] / 100, 1), round(loc[1] / 100, 1), round(loc[2] / 100 - planner.alt0, 1),
                          round(rec['ForwardSpeedMS'], 1), round(raw.steer, 2)))
    res = judge.results
    finished = bool(res) and res[-1]['gate'] == 'F'
    t_total = (res[-1]['t'] - t0) if finished else None
    minutes = max((sim.time - t0) / 60.0, 1e-6)
    misses = [r['miss'] for r in res if r['miss'] is not None]
    lines = [r['line'] for r in res if r.get('line') is not None]
    out = dict(
        completion_time_s=round(t_total, 2) if t_total is not None else None,
        finished=finished,
        gates_total=len(GATES),
        gates_missed=sum(1 for r in res if not r['passed']) + (len(GATES) - len(res)),
        missed_gates=[r['gate'] for r in res if not r['passed']],
        miss_mean_m=round(sum(misses) / len(misses), 2) if misses else None,
        miss_max_m=round(max(misses), 2) if misses else None,
        outside_max_m=round(max([r['outside'] for r in res if r['outside'] is not None] or [0.0]), 2),
        line_error_mean_m=round(sum(lines) / len(lines), 2) if lines else None,
        line_error_max_m=round(max(lines), 2) if lines else None,
        steer_reversals_per_min=round(steer_rev / minutes, 1),
        camera_reversals_per_min=round(cam_rev / minutes, 1),
        ground_contacts=contacts,
        gates=[dict(gate=r['gate'], passed=r['passed'], t=round(r['t'] - t0, 2),
                    lat=None if r['lat'] is None else round(r['lat'], 1), vert=None if r['vert'] is None else round(r['vert'], 1))
               for r in res],
    )
    if record:
        out['trace'] = trace
    return out


def tune_bot(scheme_cls, verbose=True):
    """Same tuning for every scheme's precise bot: stage 1 sweeps the control gains (ct, lag, course, rate_damp) on
    the default racing line, stage 2 the line (margin, turn_frac); the score sums both latencies (0, 100 ms) of
    100 x gates missed + completion time (s) + 2 x the largest racing-line error at a gate (m). Paste the result
    into the scheme's GAINS. About 1 minute."""
    import itertools

    def score(g):
        tot = 0.0
        for L in (0.0, 100.0):
            r = run_course(scheme_cls(), 'precise', L, gains=g)
            tot += r['gates_missed'] * 100 + (r['completion_time_s'] or 200.0) + 2 * (r['line_error_max_m'] or 50.0)
        return tot

    base = dict(scheme_cls.GAINS)
    best = None
    for ct, lag, course, rd in itertools.product((0.5, 0.8, 1.2), (0.35, 0.5, 0.65), (0.7, 1.0, 1.6), (0.3, 0.6)):
        g = dict(base, ct=ct, lag=lag, course=course, rate_damp=rd)
        s = score(g)
        if best is None or s < best[0]:
            best = (s, g)
    for margin, frac in itertools.product((5.0, 7.0, 9.0), (0.75, 0.85, 0.95)):
        g = dict(best[1], margin=margin, turn_frac=frac)
        s = score(g)
        if s < best[0]:
            best = (s, g)
    if verbose:
        print('best score %.1f gains %s' % best)
    return best[1]


def main(argv):
    if '--tune' in argv:
        argv = [a for a in argv if a != '--tune']
        tune_bot(type(load_scheme(argv[0] if argv else 'classic')))
        return
    key = 'classic'
    lat = None
    skills = ['precise', 'sloppy']
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--latency':
            lat = float(argv[i + 1])
            i += 1
        elif a == '--skill':
            skills = [argv[i + 1]]
            i += 1
        else:
            key = a
        i += 1
    lats = [lat] if lat is not None else [0.0, 100.0]
    for sk in skills:
        for L in lats:
            r = run_course(load_scheme(key), sk, L)
            print('%-8s %-7s lat %3.0f ms: time %s s, missed %d %s, miss mean/max %s/%s m, line err mean/max %s/%s m, steer rev/min %s, '
                  'cam rev/min %s, ground %d' % (key, sk, L, r['completion_time_s'], r['gates_missed'], r['missed_gates'], r['miss_mean_m'],
                                                 r['miss_max_m'], r['line_error_mean_m'], r['line_error_max_m'], r['steer_reversals_per_min'],
                                                 r['camera_reversals_per_min'], r['ground_contacts']))
            print('         gates:', ' '.join('%s%s(%s,%s)' % (g['gate'], '' if g['passed'] else '!', g['lat'], g['vert']) for g in r['gates']))


if __name__ == '__main__':
    main(sys.argv[1:])
