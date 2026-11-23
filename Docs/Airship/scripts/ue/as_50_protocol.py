"""as_50_protocol.py - the maneuver protocol, bot wiring and metrics of the control-scheme PIE harness (as_50).

Pure Python, no `unreal`. Two drivers run the SAME code:
  * Docs/Airship/scripts/ue/as_50_pie_controls.py drives it frame by frame inside the editor (PIE), and
  * the offline self-test at the bottom drives it against the bench (Docs/Airship/controls/sims/airship_sim.py), so
    the port of the metric definitions and the bot adapters can be checked against <scheme>_metrics.json without
    Unreal:  python3 Docs/Airship/scripts/ue/as_50_protocol.py --selftest classic   (one scheme per process)

The protocol is written as Python generators. A run yields actions and receives one record per frame:
  Frame(raw)  one frame of raw inputs (airship_sim.RawInput: Enhanced Input axis / button values + the control
              rotation); the driver applies it and sends back the record of that frame
  Reset(...)  put the ship at a start pose, at rest (PIE: teleport + scheme re-apply + hold re-latch; bench: a new Sim)
  Media(...)  a capture request (chase frames on / off, a key-moment still, a gate colour); the bench driver ignores it
A record (dict) carries the server ship's FAirshipFlightTelemetry fields (C++ names), ActorLocCm, VelCm, CourseDeg,
ForwardSpeed, plus 'pilot' (the pilot machine's view / screen, control rotation, camera location, the rig cosmetics
TurbineYawDeg / WheelAngleDeg / NozzlePitchDeg, the aim side), 'ground_contact' and 'shots_total'.

Metric definitions, names and code: Docs/Airship/controls/sims/metrics.py and course.py (README "Metric definitions"),
ported 1:1 (same expressions, same frame counts). PIE-only rules, all in TEST_PROTOCOL.md:
  * time zero of a maneuver segment = the first frame whose shaped controls on the pilot's machine change (the bench's
    "first frame where the pilot's own FAirshipPilotInput changes"; the wire input itself is not readable from Python);
  * BoostActive (M2 boost_duration_s) = the server's latch from the fuel: active in frame k <=> fuel after frame k-1 > 0;
  * ground contact (M11) = GroundClearanceM (nozzle exits to the ground) under 0.25 m;
  * M12 shots = cannonballs seen on the server / 2; M9 server_kick_ms = null (the impulse is not readable).
"""
import copy
import importlib
import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SIMS = os.path.normpath(os.path.join(HERE, '..', '..', 'controls', 'sims'))
PROTOCOL_VERSION = 'as_50_protocol 2026-11-23'

# scheme id (EAirshipControlScheme) -> bench key, label, Python enum name (UHT: CLASSIC, GALLEON, SKY_RACER, POINT_FLY)
SCHEMES = {0: ('classic', 'Classic (v1)', 'CLASSIC'), 1: ('galleon', 'Galleon', 'GALLEON'),
           2: ('skyracer', 'Sky Racer', 'SKY_RACER'), 3: ('pointfly', 'Point & Fly', 'POINT_FLY')}
KEY_TO_ID = dict((v[0], k) for k, v in SCHEMES.items())

START_AGL_M = 60.0          # metrics.START_AGL (M1-M10, M12)
COURSE_AGL_M = 30.0         # course.START_ALT_AGL (M11)
ORBIT_START_OFFSET_M = (0.0, 100.0)   # M12: the ship starts 100 m off the target's ... +Y (target to port, heading +X)

K0_MAX = 10                 # frames to wait for a segment's input to show on the pilot's machine before giving up
JUMP = 0.02                 # a shaped control moving this much in one frame = the new input (first frame: >= 0.07)
GROUND_CONTACT_M = 0.25     # GroundClearanceM below this = ground contact (PIE proxy for the bench's keel check)

CONTRACT_FIELDS = ('Scheme', 'ThrottleOrder', 'DriftCharge', 'bHeadingTargetActive', 'HeadingTargetDeg', 'bFreeLook')
EXTRA_FIELDS = ('DriftDir', 'DriftTier', 'TurboAlpha', 'TurboChain', 'bGunDeck', 'bGunLock')
BASE_FIELDS = ('SpeedMS', 'ForwardSpeedMS', 'LateralSpeedMS', 'AltitudeM', 'GroundClearanceM', 'VerticalSpeedMS',
               'YawRateDegS', 'RollDeg', 'PitchDeg', 'YawDeg', 'HoldAltitudeM', 'BoostFuel', 'Health', 'MaxHealth',
               'MassKg', 'Throttle', 'Steer', 'Lift', 'Strafe', 'Boost', 'bBraking', 'bDrifting', 'bHasPilot', 'bIsDead')
TELEMETRY_FIELDS = BASE_FIELDS + CONTRACT_FIELDS + EXTRA_FIELDS
SHAPED_AXES = ('Throttle', 'Steer', 'Lift', 'Strafe', 'Boost')
SHAPED_BOOLS = ('bBraking', 'bDrifting')

# nominal game seconds of each run (status / ETA and the driver's per-run time-out: 1.3 x nominal + 10 s)
RUN_NOMINAL_S = {'probe': 2.0, 'm1_m2': 28.0, 'm3_brake': 30.0, 'm3_coast': 62.0, 'm4_m5': 42.0, 'm7_climb': 7.0,
                 'm7_sink': 7.0, 'm7_step': 18.0, 'm8_hover': 6.0, 'm8_cruise': 26.0, 'm9': 28.0, 'm11_precise': 120.0,
                 'm11_sloppy': 120.0, 'm12_precise': 77.0, 'm12_sloppy': 77.0, 'xcheck_debug': 32.0,
                 'm10_steer_lat100': 25.0, 'm10_thr_lat100': 4.0, 'm11_precise_lat100': 120.0,
                 'm11_sloppy_lat100': 120.0, 'm12_precise_lat100': 77.0, 'm12_sloppy_lat100': 77.0}
RUN_MAX_S = {'m11_precise': 205.0, 'm11_sloppy': 205.0, 'm11_precise_lat100': 205.0, 'm11_sloppy_lat100': 205.0}


def base_run(name):
    """'m11_sloppy_r2_lat100' -> 'm11_sloppy_lat100' (repeats share the nominal times of their run)."""
    parts = (name or '').split('_')
    return '_'.join(p for p in parts if not (len(p) > 1 and p[0] == 'r' and p[1:].isdigit()))


def nominal_s(name):
    return RUN_NOMINAL_S.get(name, RUN_NOMINAL_S.get(base_run(name), 60.0))


def run_max_s(name):
    return RUN_MAX_S.get(name, RUN_MAX_S.get(base_run(name), 1.3 * nominal_s(name) + 10.0))


# ---------------------------------------------------------------------------------------------------------------------
# The bench modules (Docs/Airship/controls/sims): imported from their own folder (airship_sim reads its hull files
# relative to itself), reloaded in dependency order so an edited sim is picked up by a long-lived editor namespace
# ---------------------------------------------------------------------------------------------------------------------
class _Bench(object):
    A = None   # airship_sim
    C = None   # course
    M = None   # metrics


B = _Bench()


def load_bench(reload=True):
    if SIMS not in sys.path:
        sys.path.insert(0, SIMS)
    for name in ('airship_sim', 'scheme_galleon', 'scheme_skyracer', 'scheme_pointfly', 'course', 'metrics'):
        mod = sys.modules.get(name)
        mod = importlib.reload(mod) if (mod is not None and reload) else importlib.import_module(name)
        if name == 'airship_sim':
            B.A = mod
        elif name == 'course':
            B.C = mod
        elif name == 'metrics':
            B.M = mod
    return B


def sim_metrics_path(key):
    return os.path.join(SIMS, '%s_metrics.json' % key)


def load_sim_metrics(key):
    try:
        with open(sim_metrics_path(key)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------------------------------------------------
class Frame(object):
    """One frame: raw = airship_sim.RawInput (None with debug); debug = (thr, steer, lift, strafe, boost, brake) for the
    DebugSetInput cross-check, or 'clear'."""
    __slots__ = ('raw', 'seg', 'debug')

    def __init__(self, raw, seg, debug=None):
        self.raw, self.seg, self.debug = raw, seg, debug


class Reset(object):
    """Start pose at rest: area 'lane' | 'course' | 'orbit' (the driver maps it to the world), offset_m from the area
    origin, agl_m = the actor origin above the ground, yaw_deg, seed (bench wind phase; PIE: GetUniqueID() % 97),
    latency_ms (bench: 0 = host pilot, 100 = client; PIE: the net mode of the session)."""
    __slots__ = ('run', 'area', 'offset_m', 'agl_m', 'yaw_deg', 'seed', 'latency_ms')

    def __init__(self, run, area, agl_m, offset_m=(0.0, 0.0), yaw_deg=0.0, seed=1, latency_ms=0.0):
        self.run, self.area, self.agl_m, self.offset_m = run, area, agl_m, offset_m
        self.yaw_deg, self.seed, self.latency_ms = yaw_deg, seed, latency_ms


class Media(object):
    """'chase_on' (label = run), 'chase_off', 'still' (label = moment), 'gate' (label = gate, data = next / passed /
    missed)."""
    __slots__ = ('what', 'label', 'data')

    def __init__(self, what, label=None, data=None):
        self.what, self.label, self.data = what, label, data


class RunTimeout(Exception):
    """Thrown into the generator by a driver when a run exceeds its time-out: the run fails, the scheme goes on."""


class SchemeAbort(Exception):
    """Raised by the protocol when the scheme cannot be measured (input path dead, ship lost): the driver moves on to
    the next scheme."""


# ---------------------------------------------------------------------------------------------------------------------
# The Sim-like facade the bench's bots and adapters read (IMPLEMENTATION_PLAN.md 5.3)
# ---------------------------------------------------------------------------------------------------------------------
class _PilotFM(object):
    """Sky Racer's bot reads its own drift state: sky_drift_dir = the pilot's DriftDir, sh_boost = its Boost."""

    def __init__(self):
        self.sky_drift_dir = 0
        self.sh_boost = 0.0
        self.sh_steer = 0.0

    def sky_s_in(self):
        return max(-1.0, min(1.0, self.sh_steer * self.sky_drift_dir))


class _Cam(object):
    def __init__(self):
        self.control_yaw = 0.0
        self.control_pitch = -12.0
        self.view_yaw = 0.0
        self.view_pitch = -12.0


class Ctx(object):
    """One scheme pass: scheme, presets (P / PP as the bench's Sim builds them), the frame clock (time = frames since
    the run's start pose x dt, like Sim.time), the latest record, the adapters' pilot_state, and notes."""

    def __init__(self, key, cfg=None, net='host', areas=None):
        A = B.A
        self.key = key
        self.scheme_id = KEY_TO_ID[key]
        self.label = SCHEMES[self.scheme_id][1]
        self.cfg = dict(cfg or {})
        self.scheme = A.load_scheme(key)
        self.P = dict(A.FLIGHT_DEFAULTS)
        self.P.update(self.scheme.flight)
        self.PP = dict(A.PAWN_DEFAULTS)
        self.PP.update(self.scheme.pawn)
        self.dt = A.DT
        self.net = net                       # 'host' (standalone PIE / bench latency 0) or 'client' (listen PIE / 100 ms)
        self.lat_tag = 'lat0' if net == 'host' else 'lat100'
        self.latency_ms = 0.0 if net == 'host' else 100.0
        self.areas = areas or {'lane': dict(x_m=0.0, y_m=0.0, ground_m=0.0), 'course': dict(x_m=0.0, y_m=0.0, ground_m=0.0),
                               'orbit': dict(x_m=0.0, y_m=0.0, ground_m=0.0)}
        self.frame = 0
        self.time = 0.0
        self.last = None
        self.pilot_state = {}
        self.pilot_fm = _PilotFM()
        self.cam = _Cam()
        self.camera_fn = None                # bench self-test: Sim.camera_location_m (the bench's own estimate)
        self.shared = {}                     # values runs pass on: top (M2), final_rate (M4)
        self.notes = {}                      # run -> {'k0': {seg: frames}, 'warn': [...], 'status': ...}
        self.run = None
        self.missing = {}                    # telemetry field -> where it was first missing
        self.order_emul = 0
        self.prev_raw_thr = 0.0
        self.last_sig = None                 # raw_sig of the last Frame yielded
        self.log_fn = None                   # driver's logger (tag, msg)
        self.sim_ref = load_sim_metrics(key)

    # ---- the bench's Sim helpers (they only read self.P) ------------------------------------------------------------
    def rmax_deg(self, vf_cm):
        return B.A.Sim.rmax_deg(self, vf_cm)

    def top_speed_estimate(self):
        return B.A.Sim.top_speed_estimate(self)

    def hold_throttle(self, v_cm):
        return B.A.Sim.hold_throttle(self, v_cm)

    def pilot_view(self):
        return self.last['pilot']['view']

    def camera_location_m(self, view):
        if self.camera_fn is not None:
            return self.camera_fn(view)
        return tuple(self.last['pilot']['cam_loc_m'])

    def area(self, name):
        return self.areas[name]

    # ---- bookkeeping ----------------------------------------------------------------------------------------------
    def say(self, tag, msg):
        if self.log_fn is not None:
            try:
                self.log_fn(tag, msg)
                return
            except Exception:  # noqa: BLE001
                pass
        print('%s: %s' % (tag, msg))

    def warn(self, msg):
        n = self.notes.setdefault(self.run, {'k0': {}, 'warn': []})
        n['warn'].append(msg)
        self.say('WARN', '%s/%s: %s' % (self.key, self.run, msg))

    def note_k0(self, seg, k0):
        self.notes.setdefault(self.run, {'k0': {}, 'warn': []})['k0'][seg] = k0

    def begin_run(self, name):
        self.run = name
        self.frame = 0
        self.time = 0.0
        self.pilot_state = {'order': 0, 'last_raw_throttle': 0.0} if self.key == 'galleon' else {}
        self.order_emul = 0
        self.prev_raw_thr = 0.0
        self.last_sig = raw_sig(B.A.RawInput())
        self.pilot_fm = _PilotFM()
        self.notes.setdefault(name, {'k0': {}, 'warn': []})

    def missing_field(self, name, where):
        if name not in self.missing:
            self.missing[name] = where
            self.say('WARN', 'telemetry field %s missing (%s): default used' % (name, where))

    def on_frame(self, raw):
        """Called for every Frame the protocol yields: Galleon's telegraph emulation (only used when the C++ gives no
        ThrottleOrder: a raw throttle press edge steps one notch, as a fresh press does)."""
        self.last_sig = raw_sig(raw)
        if raw is None or self.key != 'galleon':
            return
        v = raw.throttle
        if v > 0.5 and self.prev_raw_thr <= 0.5:
            self.order_emul = min(3, self.order_emul + 1)
        elif v < -0.5 and self.prev_raw_thr >= -0.5:
            self.order_emul = max(-1, self.order_emul - 1)
        self.prev_raw_thr = v

    def update(self, rec, advance=True):
        """A new record (the state after the frame just run). advance=False for the start-pose record."""
        if advance:
            self.frame += 1
            self.time = self.frame * self.dt
        rec['t'] = self.time
        self.last = rec
        pv = rec['pilot']['view']
        self.cam.control_yaw = rec['pilot'].get('control_yaw', 0.0)
        self.cam.control_pitch = rec['pilot'].get('control_pitch', -12.0)
        self.cam.view_yaw, self.cam.view_pitch = self.cam.control_yaw, self.cam.control_pitch
        if self.key == 'galleon':
            o = pv.get('ThrottleOrder')
            if o is None:
                self.missing_field('ThrottleOrder', 'pilot view (Galleon order: telegraph emulated from the taps)')
                self.pilot_state['order'] = self.order_emul
            elif o < -1.5:
                if 'order_m2' not in self.pilot_state:
                    self.pilot_state['order_m2'] = True
                    self.warn('ThrottleOrder is -2 while Galleon is selected: the C++ scheme is not active? (taps emulated)')
                self.pilot_state['order'] = self.order_emul
            else:
                self.pilot_state['order'] = -1 if o <= -0.5 else int(round(max(0.0, min(1.0, o)) * 3.0))
        elif self.key == 'skyracer':
            d = pv.get('DriftDir')
            if d is None:
                self.missing_field('DriftDir', 'pilot view (Sky Racer bot: sign(Steer) while bDrifting used)')
                d = (1 if pv.get('Steer', 0.0) >= 0 else -1) if pv.get('bDrifting') else 0
            self.pilot_fm.sky_drift_dir = int(round(d))
            self.pilot_fm.sh_boost = pv.get('Boost', 0.0)
            self.pilot_fm.sh_steer = pv.get('Steer', 0.0)


def check_fields(ctx, rec):
    """Logs every contract / extra telemetry field the C++ does not provide yet (once per scheme)."""
    for k in TELEMETRY_FIELDS:
        if k not in rec:
            ctx.missing_field(k, 'server telemetry')
        if k not in rec['pilot']['view']:
            ctx.missing_field(k, 'pilot telemetry')


def derive(tele, loc_cm, vel_cm):
    """The computed keys the bench's view has: ActorLocCm, VelCm, CourseDeg (velocity heading, the yaw below 1 cm/s),
    ForwardSpeed (cm/s)."""
    tele['ActorLocCm'] = tuple(loc_cm)
    tele['VelCm'] = tuple(vel_cm)
    tele['ForwardSpeed'] = tele.get('ForwardSpeedMS', 0.0) * 100.0
    if math.hypot(vel_cm[0], vel_cm[1]) > 1.0:
        tele['CourseDeg'] = math.degrees(math.atan2(vel_cm[1], vel_cm[0]))
    else:
        tele['CourseDeg'] = tele.get('YawDeg', 0.0)
    return tele


def input_changed(prev, rec):
    a, b = prev['pilot']['view'], rec['pilot']['view']
    for k in SHAPED_AXES:
        if abs((b.get(k) or 0.0) - (a.get(k) or 0.0)) > JUMP:
            return True
    for k in SHAPED_BOOLS:
        if bool(b.get(k)) != bool(a.get(k)):
            return True
    if b.get('ThrottleOrder') is not None and b.get('ThrottleOrder') != a.get('ThrottleOrder'):
        return True
    return False


# ---------------------------------------------------------------------------------------------------------------------
# Segments (port of airship_sim.run_commands with the PIE time zero)
# ---------------------------------------------------------------------------------------------------------------------
def frame(ctx, raw, seg, debug=None):
    ctx.on_frame(raw)
    return Frame(raw, seg, debug)


def settle(ctx, seconds=2.0, neutral_raw=False, seg='settle'):
    """metrics.new_sim's run_commands(sim, Command(), 2.0) (neutral_raw: course.run_course's sim.step(RawInput()))."""
    A = B.A
    n = int(2.0 / ctx.dt) if neutral_raw else int(round(seconds / ctx.dt))
    for _ in range(n):
        raw = A.RawInput() if neutral_raw else ctx.scheme.command_raw(ctx, A.Command())
        yield frame(ctx, raw, seg)


def raw_sig(raw):
    """What the pilot does this frame (keys, buttons, the camera set), to see when a command changes the raw input."""
    if raw is None:
        return None
    return (round(raw.throttle, 4), round(raw.steer, 4), round(raw.lift, 4), round(raw.strafe, 4), bool(raw.boost),
            bool(raw.brake), bool(raw.aim), None if raw.cam_yaw is None else round(raw.cam_yaw, 3),
            None if raw.cam_pitch is None else round(raw.cam_pitch, 3))


def segment(ctx, seg, cmd_fn, n, until=None):
    """Port of airship_sim.run_commands: n frames of cmd_fn(t) (a Command through the scheme's command_raw, or a
    RawInput as it is), t in s from the segment's start.

    PIE time zero (README "Time zero"): the frames from the first frame whose RAW input differs from the frame before
    up to (not including) the first frame whose shaped controls on the pilot's machine change are the input path's
    delay. They are taken out of the log (0 frames expected in a standalone PIE: the inject call is one frame before
    the frame that uses it), so the log lines up with the bench's. Frames before the raw change stay (a scheme adapter
    can spend frames on its own, e.g. Galleon's release frame between telegraph taps: the bench counts them too). If no
    change shows within K0_MAX frames of the raw change, nothing is taken out (logged). until(log) ends the segment
    early. Returns (log, pre): pre = the record just before time zero (the state the metrics start from)."""
    A = B.A
    seg_pre = ctx.last
    pre = seg_pre
    sig_prev = ctx.last_sig
    log = []
    j = None            # index of the first raw change
    waiting = True      # raw changed, its effect not seen yet
    prev = seg_pre
    delay = 0
    while True:
        c = cmd_fn(len(log) * ctx.dt)
        raw = c if isinstance(c, A.RawInput) else ctx.scheme.command_raw(ctx, c)
        sig = raw_sig(raw)
        rec = yield frame(ctx, raw, seg)
        log.append(rec)
        idx = len(log) - 1
        if waiting:
            if j is None and sig != sig_prev:
                j = idx
            if j is not None:
                if input_changed(prev, rec):
                    waiting = False
                    delay = idx - j
                    if delay:
                        if j == 0:
                            pre = log[idx - 1]
                        del log[j:idx]
                elif idx - j + 1 >= K0_MAX:
                    waiting = False
                    ctx.warn('%s: the shaped controls did not change within %d frames of the new input: no time-zero '
                             'shift' % (seg, K0_MAX))
        prev = rec
        if waiting and j is not None:
            continue                 # do not end a segment while its input is in flight
        if (until is not None and until(log)) or len(log) >= n:
            break
    ctx.note_k0(seg, delay)
    return log, pre


def C(**kw):
    return B.A.Command(**kw)


# ---------------------------------------------------------------------------------------------------------------------
# Metric helpers (metrics.py)
# ---------------------------------------------------------------------------------------------------------------------
def _mean(v):
    return sum(v) / len(v) if v else None


def _rnd(x, n=2):
    return None if x is None else round(x, n)


def _first_time(log, fn, dt):
    for i, r in enumerate(log):
        if fn(r):
            return round((i + 1) * dt, 3)
    return None


def cannon_angles_raw(c, target_cm, rec):
    """airship_sim.Sim.cannon_angles_raw from a record: the hull's actor location and rotation, the rest muzzle
    positions and rest directions of the bench (hull-local)."""
    A = B.A
    q = A.rot2quat(rec['PitchDeg'], rec['YawDeg'], rec['RollDeg'])
    loc = rec['ActorLocCm']
    muzzle = A.add(tuple(loc), A.qrot(q, A.CANNON_MUZZLE[c]))
    to = A.qunrot(q, A.sub(target_cm, muzzle))
    rest = A.CANNON_REST_DIR[c]
    rest_flat = A.norm((rest[0], rest[1], 0.0))
    flat = (to[0], to[1], 0.0)
    yaw = math.atan2(A.cross(rest_flat, flat)[2], A.dot(rest_flat, flat)) * A.R2D
    elev = math.atan2(to[2], A.size2d(flat)) * A.R2D
    return yaw, elev, A.size(to)


# ---------------------------------------------------------------------------------------------------------------------
# Runs. Each returns {'M1.t80_s': value, ...} (dotted metric paths) and may set ctx.shared.
# ---------------------------------------------------------------------------------------------------------------------
def run_probe(ctx):
    """The Enhanced Input path reaches the pawn: throttle +1 must move the shaped throttle within 12 frames."""
    A = B.A
    yield Reset('probe', 'lane', START_AGL_M, seed=1, latency_ms=ctx.latency_ms)
    check_fields(ctx, ctx.last)
    for _ in range(15):
        yield frame(ctx, A.RawInput(), 'settle')
    pre = ctx.last['pilot']['view'].get('Throttle') or 0.0
    seen = None
    for k in range(12):
        rec = yield frame(ctx, A.RawInput(throttle=1.0), 'probe')
        th = rec['pilot']['view'].get('Throttle')
        if th is not None and abs(th - pre) > JUMP:
            seen = k
            break
    for _ in range(4):
        yield frame(ctx, A.RawInput(), 'probe_end')
    if seen is None:
        raise SchemeAbort('Enhanced Input probe: IA_AirshipThrottle +1 for 12 frames did not move the shaped Throttle on the '
                          'pilot\'s machine (injection not reaching the pawn, or the IMC / input component missing)')
    return {'_probe_frames': seen}


def cruise(ctx, run, area='lane', seed=1):
    """metrics.cruise_sim: the start pose, neutral 2 s, then 20 s of full forward drive."""
    yield Reset(run, area, START_AGL_M, seed=seed, latency_ms=ctx.latency_ms)
    yield from settle(ctx)
    log, pre = yield from segment(ctx, 'cruise', lambda t: C(thrust=1.0), int(round(20.0 / ctx.dt)))
    return log


def run_m1_m2(ctx):
    """metrics.m1_m2_m6 (+ M10 throttle lat0: the bench's M10 throttle run = the first 2 s of this drive)."""
    DT = ctx.dt
    yield Reset('m1_m2', 'lane', START_AGL_M, seed=1, latency_ms=ctx.latency_ms)
    check_fields(ctx, ctx.last)
    yield from settle(ctx)
    log, pre = yield from segment(ctx, 'drive', lambda t: C(thrust=1.0), int(round(20.0 / DT)))
    alt0 = pre['AltitudeM']
    blog, preb = yield from segment(ctx, 'boost', lambda t: C(thrust=1.0, boost=True), int(round(6.0 / DT)))
    v = [r['ForwardSpeedMS'] for r in log]
    top = _mean(v[int(17 / DT):])
    peak = max(v)
    out = {'M1.t80_s': _first_time(log, lambda r: r['ForwardSpeedMS'] >= 0.8 * top, DT),
           'M1.t63_s': _first_time(log, lambda r: r['ForwardSpeedMS'] >= 0.63 * top, DT),
           'M1.speed_at_2s_ms': _rnd(v[int(round(2 / DT)) - 1]), 'M1.speed_at_4s_ms': _rnd(v[int(round(4 / DT)) - 1])}
    pitch_min = min(r['PitchDeg'] for r in log)
    pitch_top = _mean([r['PitchDeg'] for r in log[int(17 / DT):]])
    alt_dip = alt0 - min(r['AltitudeM'] for r in log)
    v0 = preb['ForwardSpeedMS']
    bv = [r['ForwardSpeedMS'] for r in blog]
    bpeak = max(bv)
    # the server's boost latch (not in the telemetry): active in frame k <=> the fuel after frame k-1 is above 0 (and
    # it could start: fuel >= BoostMinFuelToStart before the first frame), as UpdateBoostServer / the bench's latch
    fuels = [preb.get('BoostFuel')] + [r.get('BoostFuel') for r in blog]
    active = []
    for k in range(len(blog)):
        f = fuels[k]
        if f is None:
            active.append(True)
        elif k == 0:
            active.append(f >= ctx.P['BoostMinFuelToStart'])
        else:
            active.append(active[-1] and f > 0.0)
    if preb.get('BoostFuel') is not None and preb['BoostFuel'] < ctx.P['BoostFuelMax'] - 0.5:
        ctx.warn('boost started with %.1f fuel (not full): boost_duration_s is short' % preb['BoostFuel'])
    dur = (active.index(False) if False in active else len(active)) * DT
    t90 = _first_time(blog, lambda r: r['ForwardSpeedMS'] >= v0 + 0.9 * (bpeak - v0), DT)
    out.update({'M2.top_steady_ms': _rnd(top), 'M2.top_peak_ms': _rnd(peak), 'M2.boost_peak_ms': _rnd(bpeak),
                'M2.boost_ratio': _rnd(bpeak / top, 3) if top else None, 'M2.boost_duration_s': _rnd(dur),
                'M2.boost_t90_s': t90,
                'M6.drive_pitch_min_deg': _rnd(pitch_min), 'M6.top_pitch_deg': _rnd(pitch_top),
                'M6.boost_pitch_min_deg': _rnd(min(r['PitchDeg'] for r in blog)), 'M6.drive_alt_dip_m': _rnd(alt_dip)})
    ctx.shared['top'] = top
    # M10 throttle (metrics.m10, second half): from the start pose, 2 s of forward drive
    tlog = log[:int(round(2.0 / DT))]
    out.update(m10_throttle(tlog, pre, ctx.lat_tag))
    return out


def m10_throttle(log, pre, lat):
    nz0 = pre['pilot'].get('NozzlePitchDeg')
    sp0 = pre['pilot']['screen'].get('ForwardSpeedMS')
    nozzle = None
    if nz0 is not None:
        nozzle = next((i for i in range(len(log)) if log[i]['pilot'].get('NozzlePitchDeg') is not None
                       and abs(log[i]['pilot']['NozzlePitchDeg'] - nz0) > 0.2), None)
    speed = next((i for i in range(len(log)) if log[i]['pilot']['screen']['ForwardSpeedMS'] - sp0 > 0.1), None)
    return {'M10.%s.nozzle_frames' % lat: nozzle, 'M10.%s.screen_speed_frames' % lat: speed}


def m10_steer(log, pre, final_rate, lat):
    def frames(fn):
        for i in range(len(log)):
            try:
                if fn(log[i]):
                    return i
            except TypeError:       # a cosmetic missing on this machine
                return None
        return None
    out = {}
    thr = 0.1 * final_rate if final_rate is not None else None
    r0s = pre['YawRateDegS']
    r0p = pre['pilot']['screen']['YawRateDegS']
    tb0, wh0 = pre['pilot'].get('TurbineYawDeg'), pre['pilot'].get('WheelAngleDeg')
    out['M10.%s.turbine_frames' % lat] = None if tb0 is None else frames(lambda r: abs(r['pilot']['TurbineYawDeg'] - tb0) > 0.5)
    out['M10.%s.wheel_frames' % lat] = None if wh0 is None else frames(lambda r: abs(r['pilot']['WheelAngleDeg'] - wh0) > 2.0)
    out['M10.%s.server_turn_frames' % lat] = None if thr is None else frames(lambda r: r['YawRateDegS'] - r0s > thr)
    out['M10.%s.screen_turn_frames' % lat] = None if thr is None else frames(lambda r: r['pilot']['screen']['YawRateDegS'] - r0p > thr)
    return out


def run_m3_brake(ctx):
    DT = ctx.dt
    G_MS2 = 9.81
    yield from cruise(ctx, 'm3_brake')
    log, t0 = yield from segment(ctx, 'brake', lambda t: C(brake=True), int(round(8.0 / DT)))
    v0 = t0['ForwardSpeedMS']
    p0 = t0['ActorLocCm']
    yaw0 = t0['YawDeg'] * B.A.D2R
    alt0 = t0['AltitudeM']
    v = [v0] + [r['ForwardSpeedMS'] for r in log]
    k_stop = next((i for i in range(1, len(v)) if v[i] <= 0.5), None)
    dist = None
    if k_stop is not None:
        p = log[k_stop - 1]['ActorLocCm']
        dist = ((p[0] - p0[0]) * math.cos(yaw0) + (p[1] - p0[1]) * math.sin(yaw0)) / 100.0
    decel = max(-(v[i + 1] - v[i - 1]) / (2 * DT) for i in range(1, len(v) - 1)) / G_MS2
    flare = max(r['PitchDeg'] for r in log)
    rise = max(r['AltitudeM'] for r in log) - alt0
    half = _first_time(log, lambda r: r['ForwardSpeedMS'] <= 0.5 * v0, DT)
    mean_decel = v0 / (k_stop * DT) / G_MS2 if k_stop else None
    return {'M3.start_speed_ms': _rnd(v0), 'M3.stop_time_s': _rnd(k_stop * DT if k_stop else None),
            'M3.stop_distance_m': _rnd(dist), 'M3.half_speed_s': half, 'M3.peak_decel_g': _rnd(decel),
            'M3.mean_decel_g': _rnd(mean_decel), 'M3.alt_rise_m': _rnd(rise), 'M6.brake_pitch_max_deg': _rnd(flare)}


def run_m3_coast(ctx):
    DT = ctx.dt
    yield from cruise(ctx, 'm3_coast')
    clog, c0r = yield from segment(ctx, 'coast', lambda t: C(), int(round(40.0 / DT)))
    c0 = c0r['ForwardSpeedMS']
    return {'M3.coast_half_s': _first_time(clog, lambda r: r['ForwardSpeedMS'] <= 0.5 * c0, DT)}


def run_m4_m5(ctx):
    """metrics.m4 (8 s), m5 (until 180 deg, at most 20 s) and the M10 steer run (3 s): the bench flies all three from
    the same cruise with the same command, so one turn covers them."""
    A = B.A
    DT = ctx.dt
    yield from cruise(ctx, 'm4_m5')
    n4, n5, n10 = int(round(8.0 / DT)), int(20 / DT), int(round(3.0 / DT))
    y_start = ctx.last['YawDeg']

    def until(log):
        if len(log) < n4:
            return False
        turned, prev = 0.0, y_start
        for r in log:
            turned += A.wrap180(r['YawDeg'] - prev)
            prev = r['YawDeg']
        return turned >= 180.0
    log, t0 = yield from segment(ctx, 'turn', lambda t: C(thrust=1.0, steer=1.0), n5, until=until)
    # the turn's own start (time zero may come after warm frames: recount the heading from there)
    turned, prev, n180 = 0.0, t0['YawDeg'], None
    for i, r in enumerate(log):
        turned += A.wrap180(r['YawDeg'] - prev)
        prev = r['YawDeg']
        if turned >= 180.0:
            n180 = i + 1
            break
    out = {}
    # M4
    l4 = log[:n4]
    alt0 = t0['AltitudeM']
    rr = [x['YawRateDegS'] for x in l4]
    final = _mean(rr[int(6 / DT):])
    peak = max(rr)
    last = l4[-1]
    ok = final is not None and abs(final) > 1e-6
    out.update({'M4.final_yaw_rate_degs': _rnd(final),
                'M4.t63_s': _first_time(l4, lambda x: x['YawRateDegS'] >= 0.63 * final, DT) if ok else None,
                'M4.t90_s': _first_time(l4, lambda x: x['YawRateDegS'] >= 0.9 * final, DT) if ok else None,
                'M4.overshoot_pct': _rnd(max(0.0, (peak - final) / final * 100.0), 1) if ok else None,
                'M4.bank_deg': _rnd(_mean([x['RollDeg'] for x in l4[int(6 / DT):]])),
                'M4.slip_8s_deg': _rnd(math.atan2(-last['LateralSpeedMS'], last['ForwardSpeedMS']) * A.R2D),
                'M4.speed_8s_ms': _rnd(last['SpeedMS']), 'M4.alt_loss_8s_m': _rnd(alt0 - last['AltitudeM']),
                'M4.pitch_min_deg': _rnd(min(x['PitchDeg'] for x in l4))})
    ctx.shared['final_rate'] = final
    # M5
    p0 = t0['ActorLocCm']
    y0 = t0['YawDeg']
    v0 = t0['ForwardSpeedMS']
    right0 = (-math.sin(y0 * A.D2R), math.cos(y0 * A.D2R))
    rec = log[n180 - 1] if n180 else log[min(len(log), n5) - 1]
    p = rec['ActorLocCm']
    diam = abs((p[0] - p0[0]) * right0[0] + (p[1] - p0[1]) * right0[1]) / 100.0
    out.update({'M5.time_s': _rnd(n180 * DT if n180 else None), 'M5.diameter_m': _rnd(diam),
                'M5.speed_end_ms': _rnd(rec['SpeedMS']), 'M5.speed_kept_pct': _rnd(rec['SpeedMS'] / v0 * 100.0, 1) if v0 else None})
    # M10 steer lat0 (metrics.m10, first half)
    out.update(m10_steer(log[:n10], t0, final, ctx.lat_tag))
    return out


def new_start(ctx, run):
    """metrics.new_sim: the start pose and neutral 2 s."""
    yield Reset(run, 'lane', START_AGL_M, seed=1, latency_ms=ctx.latency_ms)
    yield from settle(ctx)


def run_m7_climb(ctx):
    yield from new_start(ctx, 'm7_climb')
    log, _ = yield from segment(ctx, 'climb', lambda t: C(lift=1.0), int(round(5.0 / ctx.dt)))
    return {'M7.climb_rate_ms': _rnd(max(r['VerticalSpeedMS'] for r in log))}


def run_m7_sink(ctx):
    yield from new_start(ctx, 'm7_sink')
    log, _ = yield from segment(ctx, 'sink', lambda t: C(lift=-1.0), int(round(5.0 / ctx.dt)))
    return {'M7.sink_rate_ms': _rnd(-min(r['VerticalSpeedMS'] for r in log))}


def run_m7_step(ctx):
    DT = ctx.dt
    yield from new_start(ctx, 'm7_step')
    z0 = ctx.last['AltitudeM']
    lift, _ = yield from segment(ctx, 'step_lift', lambda t: C(lift=1.0), int(10 / DT),
                                 until=lambda log: log[-1]['AltitudeM'] >= z0 + 30.0)
    rise = len(lift) * DT
    log, _ = yield from segment(ctx, 'step_hold', lambda t: C(), int(round(6.0 / DT)))
    over = max(r['AltitudeM'] for r in log) - (z0 + 30.0)
    vz1 = abs(log[int(round(1 / DT)) - 1]['VerticalSpeedMS'])
    vz2 = abs(log[int(round(2 / DT)) - 1]['VerticalSpeedMS'])
    err5 = abs(log[int(round(5 / DT)) - 1]['AltitudeM'] - (z0 + 30.0))
    return {'M7.step30_rise_s': _rnd(rise), 'M7.step30_overshoot_m': _rnd(over), 'M7.step30_vz_1s_ms': _rnd(vz1),
            'M7.step30_vz_2s_ms': _rnd(vz2), 'M7.step30_error_5s_m': _rnd(err5)}


def run_m8_hover(ctx):
    DT = ctx.dt
    yield from new_start(ctx, 'm8_hover')
    log, _ = yield from segment(ctx, 'strafe', lambda t: C(strafe=1.0), int(round(4.0 / DT)))
    final = _mean([r['LateralSpeedMS'] for r in log[int(3 / DT):]])
    t90 = _first_time(log, lambda r: r['LateralSpeedMS'] >= 0.9 * final, DT) if final is not None else None
    return {'M8.t90_s': t90, 'M8.strafe_speed_ms': _rnd(final)}


def run_m8_cruise(ctx):
    DT = ctx.dt
    yield from cruise(ctx, 'm8_cruise')
    log, _ = yield from segment(ctx, 'strafe', lambda t: C(thrust=1.0, strafe=1.0), int(round(4.0 / DT)))
    return {'M8.strafe_speed_cruise_ms': _rnd(_mean([r['LateralSpeedMS'] for r in log[int(3 / DT):]]))}


def run_m9(ctx):
    A = B.A
    DT = ctx.dt
    yield from cruise(ctx, 'm9')
    log, t0 = yield from segment(ctx, 'drift', lambda t: C(thrust=1.0, steer=1.0, drift=True), int(round(3.0 / DT)))
    v0 = t0['ForwardSpeedMS']
    slip = [math.atan2(-r['LateralSpeedMS'], r['ForwardSpeedMS']) * A.R2D for r in log]
    drifting = [bool(r.get('bDrifting')) for r in log]
    v_end = log[-1]['SpeedMS']
    rate = _mean([r['YawRateDegS'] for r in log[int(1 / DT):]])
    log2, _ = yield from segment(ctx, 'drift_exit', lambda t: C(thrust=1.0), int(round(3.0 / DT)))
    allr = log + log2
    k = next((i for i in range(len(log), len(allr)) if not allr[i].get('bDrifting')), None)
    kick = None
    if k is not None and k + 2 < len(allr):
        kick = allr[k + 2]['ForwardSpeedMS'] - allr[k - 1]['ForwardSpeedMS']
    server_kick = None
    if any('Debug' in r for r in allr):          # bench self-test only: the impulse the server paid
        server_kick = _rnd(max(r.get('Debug', {}).get('DriftKick', 0.0) for r in allr) / 100.0)
    return {'M9.slip_1s_deg': _rnd(slip[int(1 / DT) - 1]), 'M9.slip_2s_deg': _rnd(slip[int(2 / DT) - 1]),
            'M9.slip_3s_deg': _rnd(slip[-1]), 'M9.drift_frames_pct': _rnd(100.0 * sum(drifting) / len(drifting), 1),
            'M9.yaw_rate_degs': _rnd(rate), 'M9.speed_kept_pct': _rnd(v_end / v0 * 100.0, 1) if v0 else None,
            'M9.exit_kick_ms': _rnd(kick), 'M9.server_kick_ms': server_kick}


STILL_AT_GATE = {'S3': 'slalom', 'H1': 'hairpin_apex', 'F': 'finish'}


def run_m11(ctx, skill, rep=None):
    """course.run_course (the gate course, M11), the same loop and summary, plus the chase capture and the six key-moment
    stills for the judges (precise bot, host only, by default). rep = 2, 3, ...: a repeat (the same bot and seed; the
    wind phase and the start differ by the run's start time), reported in meta.repeats, not in the M11 keys."""
    A, CO = B.A, B.C
    DT = ctx.dt
    lat = ctx.lat_tag
    name = 'm11_%s' % skill + ('_r%d' % rep if rep else '') + ('' if lat == 'lat0' else '_' + lat)
    area = ctx.area('course')
    yield Reset(name, 'course', COURSE_AGL_M, seed=7, latency_ms=ctx.latency_ms)
    sk = CO.Skill(skill)
    alt0 = area['ground_m'] + CO.START_ALT_AGL
    planner = CO.CoursePlanner(ctx, alt0, start_xy=(area['x_m'], area['y_m']))
    judge = CO.GateJudge(planner)
    bot = CO.Bot(ctx, planner, sk, seed=7)
    yield from settle(ctx, neutral_raw=True)
    t0 = ctx.time
    capture = (skill in tuple(ctx.cfg.get('capture_skills', ('precise',))) and not rep
               and (lat == 'lat0' or ctx.cfg.get('listen_captures')))
    gates = CO.GATES
    if capture:
        yield Media('chase_on', name)
        yield Media('still', 'start')
    yield Media('gate', gates[0][0], 'next')
    ctx.shared['next_gate'] = gates[0][0]
    timeout = 200.0
    steer_sign, steer_rev = 0, 0
    cam_sign, cam_rev, prev_cam = 0, 0, None
    contacts, was_contact = 0, False
    n = 0
    n_res = 0
    shots = {'climb': False, 'drift': False}
    rmax_frac = 0.85
    while ctx.time - t0 < timeout and planner.i < len(gates):
        raw = bot.raw()
        rec = yield frame(ctx, raw, 'course')
        judge.update(ctx, rec)
        n += 1
        s = raw.steer
        if abs(s) > 0.1:
            sg = 1 if s > 0 else -1
            if steer_sign and sg != steer_sign:
                steer_rev += 1
            steer_sign = sg
        cy = rec['pilot']['control_yaw']
        if prev_cam is not None and raw.look:
            dcy = A.wrap180(cy - prev_cam) / DT
            if abs(dcy) > 5.0:
                sg = 1 if dcy > 0 else -1
                if cam_sign and sg != cam_sign:
                    cam_rev += 1
                cam_sign = sg
        prev_cam = cy
        if rec['ground_contact'] and not was_contact:
            contacts += 1
        was_contact = rec['ground_contact']
        # ---- judges' media (no effect on the flight) ----
        done = [r['gate'] for r in judge.results]
        if len(judge.results) != n_res:
            for res in judge.results[n_res:]:
                yield Media('gate', res['gate'], 'passed' if res['passed'] else 'missed')
                if capture and res['gate'] in STILL_AT_GATE:
                    yield Media('still', STILL_AT_GATE[res['gate']])
            n_res = len(judge.results)
            if planner.i < len(gates):
                yield Media('gate', gates[planner.i][0], 'next')
                ctx.shared['next_gate'] = gates[planner.i][0]
        if capture and not shots['climb'] and 'H2' in done and (rec['AltitudeM'] >= alt0 + 25.0 or 'C' in done):
            shots['climb'] = True
            yield Media('still', 'climb')
        if capture and not shots['drift']:
            pv = rec['pilot']['view']
            hot = bool(rec.get('bDrifting')) or (rec.get('Boost') or 0.0) > 0.5 or (rec.get('TurboAlpha') or 0.0) > 0.2
            if not hot and 'S5' in done and abs(rec['YawRateDegS']) >= rmax_frac * ctx.rmax_deg(pv['ForwardSpeed']):
                hot = True          # nobody drifts or boosts on this scheme's line: the hardest turning moment instead
            if hot or 'H2' in done:
                shots['drift'] = True
                yield Media('still', 'drift_boost' if hot else 'drift_boost_none')
    if capture:
        yield Media('chase_off')
    res = judge.results
    finished = bool(res) and res[-1]['gate'] == 'F'
    t_total = (res[-1]['t'] - t0) if finished else None
    minutes = max((ctx.time - t0) / 60.0, 1e-6)
    misses = [r['miss'] for r in res if r['miss'] is not None]
    lines = [r['line'] for r in res if r.get('line') is not None]
    out = dict(
        completion_time_s=round(t_total, 2) if t_total is not None else None,
        finished=finished,
        gates_total=len(gates),
        gates_missed=sum(1 for r in res if not r['passed']) + (len(gates) - len(res)),
        missed_gates=[r['gate'] for r in res if not r['passed']],
        miss_mean_m=round(sum(misses) / len(misses), 2) if misses else None,
        miss_max_m=round(max(misses), 2) if misses else None,
        outside_max_m=round(max([r['outside'] for r in res if r['outside'] is not None] or [0.0]), 2),
        line_error_mean_m=round(sum(lines) / len(lines), 2) if lines else None,
        line_error_max_m=round(max(lines), 2) if lines else None,
        steer_reversals_per_min=round(steer_rev / minutes, 1),
        camera_reversals_per_min=round(cam_rev / minutes, 1),
        ground_contacts=contacts,
    )
    gl = [dict(gate=r['gate'], passed=r['passed'], t=round(r['t'] - t0, 2),
               lat=None if r['lat'] is None else round(r['lat'], 1), vert=None if r['vert'] is None else round(r['vert'], 1))
          for r in res]
    ctx.notes.setdefault(ctx.run, {'k0': {}, 'warn': []})['gates'] = gl
    if rep:
        return dict(('_repeat.%s.%s' % (name, k), v) for k, v in out.items())
    return dict(('M11.%s.%s.%s' % (skill, lat, k), v) for k, v in out.items())


def run_m12(ctx, skill):
    """metrics.m12 (broadside), the same loop: the OrbitPlanner bot keeps the target abeam to port and fires whenever it
    has a solution; stats over 60 s after a 15 s run-in."""
    A, CO, M = B.A, B.C, B.M
    DT = ctx.dt
    lat = ctx.lat_tag
    name = 'm12_%s' % skill + ('' if lat == 'lat0' else '_' + lat)
    area = ctx.area('orbit')
    yield Reset(name, 'orbit', START_AGL_M, offset_m=ORBIT_START_OFFSET_M, seed=3, latency_ms=ctx.latency_ms)
    alt = area['ground_m'] + START_AGL_M
    target = (area['x_m'], area['y_m'], alt)
    top = ctx.shared.get('top')
    if top is None:
        top = ((ctx.sim_ref or {}).get('M2') or {}).get('top_steady_ms') or ctx.top_speed_estimate()
        ctx.warn('M2 top speed not measured in this pass: the sim\'s %.2f m/s used for the 60 %% orbit speed' % top)
    planner = M.OrbitPlanner(target, 100.0, 0.6 * top)
    bot = CO.Bot(ctx, planner, CO.Skill(skill), seed=11)
    yield from settle(ctx)
    n_run, n_meas = int(15 / DT), int(60 / DT)
    stats = dict(arc=0, arc_both=0, rng=0, spd=0, cam=0, sol=0)
    ranges, yaws, elevs = [], [], []
    shots0 = None
    PP = ctx.PP
    tgt_cm = (target[0] * 100.0, target[1] * 100.0, target[2] * 100.0)
    capture = skill in tuple(ctx.cfg.get('capture_skills', ('precise',))) and (lat == 'lat0' or ctx.cfg.get('listen_captures'))
    for i in range(n_run + n_meas):
        raw = bot.raw()
        tele = ctx.last
        ins = []
        for c in (0, 1):
            yaw_raw, elev_raw, _ = cannon_angles_raw(c, tgt_cm, tele)
            ins.append(abs(yaw_raw) <= PP['CannonYawLimitDeg'] and PP['CannonElevMinDeg'] <= elev_raw <= PP['CannonElevMaxDeg'])
            if c == 0:
                yaws.append(yaw_raw)
                elevs.append(elev_raw)
        loc = tele['ActorLocCm']
        rng_m = math.sqrt(sum((loc[k] - tgt_cm[k]) ** 2 for k in range(3))) / 100.0
        in_rng = 80.0 <= rng_m <= 120.0
        spd = tele['ForwardSpeedMS'] >= 0.5 * top
        cam = tele['pilot'].get('aim_side') == 'port'
        sol = any(ins) and in_rng and spd and cam
        raw.fire = sol
        rec = yield frame(ctx, raw, 'orbit')
        if i == n_run:
            shots0 = rec.get('shots_total', 0)
        if capture and i == n_run + n_meas // 2:
            yield Media('still', 'broadside')
        if i >= n_run:
            stats['arc'] += any(ins)
            stats['arc_both'] += all(ins)
            stats['rng'] += in_rng
            stats['spd'] += spd
            stats['cam'] += cam
            stats['sol'] += sol
            ranges.append(rng_m)
    m = n_meas
    out = dict(
        in_arc_pct=_rnd(100.0 * stats['arc'] / m, 1), in_arc_both_pct=_rnd(100.0 * stats['arc_both'] / m, 1),
        in_range_pct=_rnd(100.0 * stats['rng'] / m, 1), speed_ok_pct=_rnd(100.0 * stats['spd'] / m, 1),
        camera_port_pct=_rnd(100.0 * stats['cam'] / m, 1), firing_solution_pct=_rnd(100.0 * stats['sol'] / m, 1),
        shots_fired=(ctx.last.get('shots_total', 0) - (shots0 or 0)) // 2, range_mean_m=_rnd(_mean(ranges)),
        beam_yaw_mean_deg=_rnd(_mean(yaws[n_run:])), elev_mean_deg=_rnd(_mean(elevs[n_run:])),
        elev_max_deg=_rnd(max(elevs[n_run:])))
    return dict(('M12.%s.%s.%s' % (skill, lat, k), v) for k, v in out.items())


def run_xcheck(ctx):
    """Classic only (optional): the M1 drive and the M4 turn again through DebugSetInput (it bypasses the pilot-side
    input path), compared with the injected runs. A difference points at the input path, not the flight model."""
    DT = ctx.dt
    yield Reset('xcheck_debug', 'lane', START_AGL_M, seed=1, latency_ms=ctx.latency_ms)
    for _ in range(int(round(2.0 / DT))):
        yield frame(ctx, None, 'settle', (0.0, 0.0, 0.0, 0.0, False, False))
    log = []
    for _ in range(int(round(20.0 / DT))):
        rec = yield frame(ctx, None, 'drive', (1.0, 0.0, 0.0, 0.0, False, False))
        log.append(rec)
    tlog = []
    for _ in range(int(round(8.0 / DT))):
        rec = yield frame(ctx, None, 'turn', (1.0, 1.0, 0.0, 0.0, False, False))
        tlog.append(rec)
    yield frame(ctx, None, 'clear', 'clear')
    v = [r['ForwardSpeedMS'] for r in log]
    top = _mean(v[int(17 / DT):])
    rr = [x['YawRateDegS'] for x in tlog]
    final = _mean(rr[int(6 / DT):])
    return {'_xcheck.top_steady_ms': _rnd(top), '_xcheck.t80_s': _first_time(log, lambda r: r['ForwardSpeedMS'] >= 0.8 * top, DT),
            '_xcheck.final_yaw_rate_degs': _rnd(final),
            '_xcheck.t63_s': _first_time(tlog, lambda x: x['YawRateDegS'] >= 0.63 * final, DT) if final else None,
            '_xcheck.injected_top_steady_ms': _rnd(ctx.shared.get('top')),
            '_xcheck.injected_final_yaw_rate_degs': _rnd(ctx.shared.get('final_rate'))}


def plan(ctx):
    """The runs of one scheme pass, in order (M2's top speed feeds M12, so m1_m2 comes first)."""
    if ctx.net == 'client':
        runs = [('probe', run_probe), ('m10_steer_lat100', run_m10_steer_lat), ('m10_thr_lat100', run_m10_thr_lat),
                ('m11_precise_lat100', lambda c: run_m11(c, 'precise')), ('m11_sloppy_lat100', lambda c: run_m11(c, 'sloppy')),
                ('m12_precise_lat100', lambda c: run_m12(c, 'precise')), ('m12_sloppy_lat100', lambda c: run_m12(c, 'sloppy'))]
    else:
        runs = [('probe', run_probe), ('m1_m2', run_m1_m2), ('m3_brake', run_m3_brake), ('m3_coast', run_m3_coast),
                ('m4_m5', run_m4_m5), ('m7_climb', run_m7_climb), ('m7_sink', run_m7_sink), ('m7_step', run_m7_step),
                ('m8_hover', run_m8_hover), ('m8_cruise', run_m8_cruise), ('m9', run_m9),
                ('m11_precise', lambda c: run_m11(c, 'precise')), ('m11_sloppy', lambda c: run_m11(c, 'sloppy')),
                ('m12_precise', lambda c: run_m12(c, 'precise')), ('m12_sloppy', lambda c: run_m12(c, 'sloppy'))]
        if ctx.key == 'classic' and ctx.cfg.get('classic_crosscheck'):
            runs.append(('xcheck_debug', run_xcheck))
    reps = int(ctx.cfg.get('sloppy_repeats', 1) or 1)
    if reps > 1:
        i = [n for n, _ in runs].index('m11_sloppy' + ('' if ctx.net == 'host' else '_lat100')) + 1
        for k in range(reps, 1, -1):
            runs.insert(i, ('m11_sloppy_r%d' % k + ('' if ctx.net == 'host' else '_lat100'), lambda c, k=k: run_m11(c, 'sloppy', rep=k)))
        runs[i:i + reps - 1] = sorted(runs[i:i + reps - 1], key=lambda x: x[0])
    only = ctx.cfg.get('runs')
    if only:
        runs = [r for r in runs if r[0] in only or r[0] == 'probe']
    return runs


def run_m10_steer_lat(ctx):
    """metrics.m10 steer for a client pilot: the cruise, then 3 s of forward + full steer."""
    DT = ctx.dt
    yield from cruise(ctx, 'm10_steer_lat100')
    log, pre = yield from segment(ctx, 'turn', lambda t: C(thrust=1.0, steer=1.0), int(round(3.0 / DT)))
    final = ctx.shared.get('final_rate')
    if final is None:
        final = ((ctx.sim_ref or {}).get('M4') or {}).get('final_yaw_rate_degs')
        ctx.warn('M4 final turn rate from the sim (%s deg/s) for the 10 %% threshold' % final)
    return m10_steer(log, pre, final, ctx.lat_tag)


def run_m10_thr_lat(ctx):
    DT = ctx.dt
    yield from new_start(ctx, 'm10_thr_lat100')
    log, pre = yield from segment(ctx, 'drive', lambda t: C(thrust=1.0), int(round(2.0 / DT)))
    return m10_throttle(log, pre, ctx.lat_tag)


def scheme_pass(ctx):
    """All runs of one scheme; a run that fails (exception, time-out) is logged and the next one starts. SchemeAbort
    ends the pass. Returns {run: {metric path: value} or None}; the same dict is ctx.frags while the pass runs (a
    driver that stops early writes what is there)."""
    frags = getattr(ctx, 'frags', None)
    if frags is None:
        frags = {}
    ctx.frags = frags
    for name, fn in plan(ctx):
        ctx.run = name
        ctx.notes.setdefault(name, {'k0': {}, 'warn': []})
        try:
            frags[name] = yield from fn(ctx)
            ctx.notes[name]['status'] = 'ok'
        except SchemeAbort:
            ctx.notes[name]['status'] = 'abort'
            raise
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            ctx.notes[name]['status'] = 'failed: %s' % (e.__class__.__name__ if isinstance(e, RunTimeout) else tb.strip().splitlines()[-1])
            ctx.notes[name]['trace'] = tb[-2000:]
            ctx.say('FAIL', '%s/%s failed: %s' % (ctx.key, name, tb.strip().splitlines()[-1]))
            frags[name] = None
    return frags


# ---------------------------------------------------------------------------------------------------------------------
# metrics.json (the sims' keys)
# ---------------------------------------------------------------------------------------------------------------------
def _blank(d):
    if isinstance(d, dict):
        return dict((k, _blank(v)) for k, v in d.items())
    return None


FALLBACK_KEYS = {
    'M1': ['t80_s', 't63_s', 'speed_at_2s_ms', 'speed_at_4s_ms'],
    'M2': ['top_steady_ms', 'top_peak_ms', 'boost_peak_ms', 'boost_ratio', 'boost_duration_s', 'boost_t90_s'],
    'M3': ['start_speed_ms', 'stop_time_s', 'stop_distance_m', 'half_speed_s', 'peak_decel_g', 'mean_decel_g', 'coast_half_s', 'alt_rise_m'],
    'M4': ['final_yaw_rate_degs', 't63_s', 't90_s', 'overshoot_pct', 'bank_deg', 'slip_8s_deg', 'speed_8s_ms', 'alt_loss_8s_m', 'pitch_min_deg'],
    'M5': ['time_s', 'diameter_m', 'speed_end_ms', 'speed_kept_pct'],
    'M6': ['drive_pitch_min_deg', 'top_pitch_deg', 'boost_pitch_min_deg', 'drive_alt_dip_m', 'brake_pitch_max_deg'],
    'M7': ['climb_rate_ms', 'sink_rate_ms', 'step30_rise_s', 'step30_overshoot_m', 'step30_vz_1s_ms', 'step30_vz_2s_ms', 'step30_error_5s_m'],
    'M8': ['t90_s', 'strafe_speed_ms', 'strafe_speed_cruise_ms'],
    'M9': ['slip_1s_deg', 'slip_2s_deg', 'slip_3s_deg', 'drift_frames_pct', 'yaw_rate_degs', 'speed_kept_pct', 'exit_kick_ms', 'server_kick_ms'],
}
M10_KEYS = ['turbine_frames', 'wheel_frames', 'server_turn_frames', 'screen_turn_frames', 'nozzle_frames', 'screen_speed_frames']
M11_KEYS = ['completion_time_s', 'finished', 'gates_total', 'gates_missed', 'missed_gates', 'miss_mean_m', 'miss_max_m',
            'outside_max_m', 'line_error_mean_m', 'line_error_max_m', 'steer_reversals_per_min', 'camera_reversals_per_min',
            'ground_contacts']
M12_KEYS = ['in_arc_pct', 'in_arc_both_pct', 'in_range_pct', 'speed_ok_pct', 'camera_port_pct', 'firing_solution_pct',
            'shots_fired', 'range_mean_m', 'beam_yaw_mean_deg', 'elev_mean_deg', 'elev_max_deg']


def template(key):
    ref = load_sim_metrics(key)
    if ref:
        return dict(('M%d' % i, _blank(ref.get('M%d' % i, {}))) for i in range(1, 13))
    t = dict((m, dict((k, None) for k in ks)) for m, ks in FALLBACK_KEYS.items())
    t['M10'] = dict((lat, dict((k, None) for k in M10_KEYS)) for lat in ('lat0', 'lat100'))
    t['M11'] = dict((sk, dict((lat, dict((k, None) for k in M11_KEYS)) for lat in ('lat0', 'lat100'))) for sk in ('precise', 'sloppy'))
    t['M12'] = dict((sk, dict((lat, dict((k, None) for k in M12_KEYS)) for lat in ('lat0', 'lat100'))) for sk in ('precise', 'sloppy'))
    return t


def put(d, path, value):
    parts = path.split('.')
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


def assemble(key, frags, base=None):
    """Merges the runs' {path: value} into the M1..M12 structure of <key>_metrics.json (unmeasured keys stay null).
    base: an existing PIE metrics.json to fill (the listen pass adds the lat100 keys to the standalone results)."""
    out = copy.deepcopy(base) if base else template(key)
    for m in ('M%d' % i for i in range(1, 13)):
        out.setdefault(m, {})
    extra = {}
    for name, fr in (frags or {}).items():
        if not fr:
            continue
        for path, v in fr.items():
            if path.startswith('_'):
                extra[path.lstrip('_')] = v
            else:
                put(out, path, v)
    return out, extra


# ---------------------------------------------------------------------------------------------------------------------
# compare.md: every metric x scheme, PIE next to the sim
# ---------------------------------------------------------------------------------------------------------------------
def flat(d, prefix=''):
    out = []
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.extend(flat(v, prefix + k + '.'))
        else:
            out.append((prefix + k, v))
    return out


def _cell(v):
    if v is None:
        return '-'
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, float):
        t = ('%.3f' if abs(v) < 10 else ('%.2f' if abs(v) < 1000 else '%.0f')) % v
        return t.rstrip('0').rstrip('.') if '.' in t else t
    if isinstance(v, list):
        return ','.join(str(x) for x in v) if v else 'none'
    return str(v)


def deviates(pie, sim):
    if isinstance(pie, bool) or isinstance(sim, bool) or not isinstance(pie, (int, float)) or not isinstance(sim, (int, float)):
        return False
    return abs(pie - sim) > max(0.15 * abs(sim), 0.5)


def write_compare(root, keys=None, out_path=None, extra_lines=None):
    """root = Saved/Airship/controls. Reads <root>/<key>/metrics.json (PIE) and the sims' <key>_metrics.json."""
    keys = keys or [SCHEMES[i][0] for i in sorted(SCHEMES)]
    pie, sim, labels = {}, {}, {}
    for k in keys:
        labels[k] = SCHEMES[KEY_TO_ID[k]][1]
        try:
            with open(os.path.join(root, k, 'metrics.json')) as f:
                pie[k] = json.load(f)
        except (OSError, ValueError):
            pie[k] = None
        sim[k] = load_sim_metrics(k)
    info = {}
    try:
        load_bench(reload=False)
        info = B.M.METRIC_INFO
    except Exception:  # noqa: BLE001
        pass
    L = ['# Airship controls: PIE against the sim', '',
         'Written by `%s` on %s. Each cell is **PIE (sim)**: the PIE value from `Saved/Airship/controls/<scheme>/metrics.json`, '
         'the sim prediction from `Docs/Airship/controls/sims/<scheme>_metrics.json`. `!` marks a PIE value more than 15 %% '
         '(and more than 0.5) away from the sim. `-` = not measured (the standalone pass has no lat100 values; M9 '
         'server_kick_ms is sim only). Definitions: `Docs/Airship/controls/sims/README.md` and `Docs/Airship/controls/TEST_PROTOCOL.md`.'
         % (PROTOCOL_VERSION, time.strftime('%Y-%m-%d %H:%M')), '']
    L.append('| Scheme | PIE run | Notes |')
    L.append('|---|---|---|')
    for k in keys:
        p = pie[k]
        if not p:
            L.append('| %s | not run | |' % labels[k])
            continue
        meta = p.get('meta', {})
        bad = [n for n, r in (meta.get('runs') or {}).items() if str(r.get('status', '')).startswith(('failed', 'abort'))]
        L.append('| %s | %s, %s, %s game s | %s%s |' % (labels[k], meta.get('generated'), meta.get('net'), meta.get('runtime_game_s'),
                                                     ('failed runs: %s; ' % ', '.join(bad)) if bad else '',
                                                     ('missing telemetry: %s' % ', '.join(sorted(meta.get('telemetry_missing') or []))) or ''))
    L.append('')
    for m in ('M%d' % i for i in range(1, 13)):
        mi = info.get(m, {})
        L.append('## %s %s' % (m, mi.get('name', '')))
        if mi:
            L.append('')
            L.append('%s. Target band: %s.' % (mi.get('definition', ''), mi.get('target', '')))
        L.append('')
        L.append('| metric | ' + ' | '.join(labels[k] for k in keys) + ' |')
        L.append('|---|' + '---|' * len(keys))
        rows = []
        for k in keys:
            for mp, _ in flat((sim[k] or {}).get(m) or {}) + flat(((pie[k] or {}).get(m)) or {}):
                if mp not in rows:
                    rows.append(mp)
        pf = dict((k, dict(flat(((pie[k] or {}).get(m)) or {}))) for k in keys)
        sf = dict((k, dict(flat((sim[k] or {}).get(m) or {}))) for k in keys)
        for mp in rows:
            cells = []
            for k in keys:
                pv, sv = pf[k].get(mp), sf[k].get(mp)
                flag = ' !' if deviates(pv, sv) else ''
                cells.append('%s (%s)%s' % (_cell(pv), _cell(sv), flag))
            L.append('| %s | %s |' % (mp, ' | '.join(cells)))
        L.append('')
    L.append('## Run notes')
    L.append('')
    for k in keys:
        p = pie[k]
        if not p:
            continue
        meta = p.get('meta', {})
        L.append('### %s' % labels[k])
        L.append('')
        sc = meta.get('scheme_confirm')
        if sc:
            L.append('* scheme confirm: %s' % json.dumps(sc))
        for n, r in (meta.get('runs') or {}).items():
            k0 = r.get('k0') or {}
            late = dict((s, v) for s, v in k0.items() if v)
            L.append('* %s: %s, %s game s%s%s' % (n, r.get('status'), r.get('game_s'),
                                               (', input seen late (frames) %s' % late) if late else '',
                                               (', warnings: %s' % '; '.join(r.get('warn') or [])) if r.get('warn') else ''))
        if meta.get('xcheck'):
            L.append('* DebugSetInput cross-check: %s' % json.dumps(meta['xcheck']))
        for tagm, src in (('standalone', meta), ('listen', meta.get('listen_pass') or {})):
            reps = src.get('repeats') or {}
            if reps:
                lat = 'lat0' if tagm == 'standalone' else 'lat100'
                first = (((p.get('M11') or {}).get('sloppy') or {}).get(lat)) or {}
                cells = ['first run: %s missed %s, %s s' % (first.get('gates_missed'), _cell(first.get('missed_gates')), first.get('completion_time_s'))]
                gm = [first.get('gates_missed')]
                for n in sorted(reps):
                    v = reps[n]
                    gm.append(v.get('gates_missed'))
                    cells.append('%s: %s missed %s, %s s' % (n, v.get('gates_missed'), _cell(v.get('missed_gates')), v.get('completion_time_s')))
                gm = sorted(x for x in gm if x is not None)
                med = gm[len(gm) // 2] if gm else None
                L.append('* sloppy course, %d runs (%s): **median %s gates missed** (judge on this: the bench\'s sloppy bot moves by '
                         '1-2 gates with the wind phase alone); %s' % (len(gm), lat, med, '; '.join(cells)))
        if meta.get('inertia_log'):
            L.append('* inertia / telemetry log: %s' % ' | '.join(meta['inertia_log'][:6]))
        media = meta.get('media') or {}
        if media:
            L.append('* media: %s' % ', '.join('%s `%s`' % (a, b) for a, b in media.items()))
        L.append('')
    for line in (extra_lines or []):
        L.append(line)
    out_path = out_path or os.path.join(root, 'compare.md')
    with open(out_path, 'w') as f:
        f.write('\n'.join(L) + '\n')
    return out_path


# ---------------------------------------------------------------------------------------------------------------------
# Offline self-test: the protocol against the bench
# ---------------------------------------------------------------------------------------------------------------------
def _sim_record(sim, srec, ctx):
    """A bench frame record in the PIE record format (only what PIE can read)."""
    A = B.A
    server = dict((k, srec[k]) for k in TELEMETRY_FIELDS if k in srec)
    derive(server, srec['ActorLocCm'], srec['VelCm'])
    if 'Debug' in srec:
        server['Debug'] = srec['Debug']
    scr = srec['pilot']['screen'] if 'pilot' in srec else srec
    view = dict((k, scr[k]) for k in TELEMETRY_FIELDS if k in scr)
    derive(view, scr['ActorLocCm'], scr['VelCm'])
    if sim.net == 'client':
        # PIE: the client copy's telemetry has its OWN shaped controls (and drift / order state), the physics replicated
        fm = sim.pilot_fm
        view.update(Throttle=fm.sh_throttle, Steer=fm.sh_steer, Lift=fm.sh_lift, Strafe=fm.sh_strafe, Boost=fm.sh_boost,
                    bBraking=fm.b_brake, bDrifting=fm.b_drifting)
        if hasattr(fm, 'sky_drift_dir'):
            view['DriftDir'] = fm.sky_drift_dir
        if hasattr(fm, 'order'):
            view['ThrottleOrder'] = {-1: -1.0, 0: 0.0, 1: 1.0 / 3.0, 2: 2.0 / 3.0, 3: 1.0}.get(fm.order, 0.0)
    p = srec.get('pilot', {})
    rec = dict(server)
    rec['pilot'] = {'view': view, 'screen': view, 'control_yaw': sim.cam.control_yaw, 'control_pitch': sim.cam.control_pitch,
                    'cam_loc_m': sim.camera_location_m(scr), 'TurbineYawDeg': p.get('TurbineYawDeg', sim.anim.turbine_yaw),
                    'WheelAngleDeg': p.get('WheelAngleDeg', sim.anim.wheel), 'NozzlePitchDeg': p.get('NozzlePitchDeg', 0.0),
                    'aim_side': sim.aim_side}
    rec['ground_contact'] = bool(srec.get('ground_contact', False))
    rec['shots_total'] = len(sim.cannon_shots)
    return rec


def selftest(key, net='host', verbose=True, shared=None):
    """Runs the protocol on the bench and compares with Docs/Airship/controls/sims/<key>_metrics.json. Returns
    (assembled metrics, list of (path, protocol value, sim value) that differ, ctx). shared: the host pass's
    ctx.shared (unrounded M2 top speed, M4 final turn rate) for a client pass, as the PIE listen pass reads them from
    meta.shared of the standalone metrics.json."""
    load_bench()
    A = B.A
    ctx = Ctx(key, {'classic_crosscheck': False}, net=net)
    ctx.shared.update(shared or {})
    ref = load_sim_metrics(key) or {}
    gen = scheme_pass(ctx)
    sim = None
    value = None
    t_start = time.time()
    while True:
        try:
            item = gen.send(value)
        except StopIteration as e:
            frags = e.value
            break
        if isinstance(item, Reset):
            sim = A.Sim(A.load_scheme(key), latency_ms=item.latency_ms, alt_agl=item.agl_m, pos_m=tuple(item.offset_m),
                        yaw_deg=item.yaw_deg, seed=item.seed)
            ctx.camera_fn = sim.camera_location_m
            if item.area == 'orbit':      # metrics.m12: the camera's aim ray hits the 6 m target (PIE: TEMP_AS50_Target)
                ar = ctx.area('orbit')
                sim.aim_targets = [((ar['x_m'] * 100.0, ar['y_m'] * 100.0, (ar['ground_m'] + START_AGL_M) * 100.0), 600.0)]
            t = sim.tele()
            srec = dict(t)
            srec['pilot'] = {'screen': t if sim.net == 'host' else sim.pilot_view(), 'TurbineYawDeg': sim.anim.turbine_yaw,
                             'WheelAngleDeg': sim.anim.wheel, 'NozzlePitchDeg': 0.0}
            ctx.begin_run(item.run)
            rec = _sim_record(sim, srec, ctx)
            ctx.update(rec, advance=False)
            value = rec
        elif isinstance(item, Frame):
            if item.debug is not None:
                d = item.debug
                raw = A.RawInput() if d == 'clear' else A.RawInput(throttle=d[0], steer=d[1], lift=d[2], strafe=d[3], boost=d[4], brake=d[5])
            else:
                raw = item.raw
                if key == 'pointfly' and raw.look:
                    raw = raw.copy()         # PIE never injects IA_AirshipLook for Point & Fly: an absolute set
                    raw.look = False
            srec = sim.step(raw)
            rec = _sim_record(sim, srec, ctx)
            ctx.update(rec)
            value = rec
        else:
            value = None
    out, extra = assemble(key, frags)
    lat = 'lat0' if net == 'host' else 'lat100'
    diffs = []
    for m in ('M%d' % i for i in range(1, 13)):
        for path, pv in flat(out.get(m) or {}):
            is100 = 'lat100' in path.split('.')
            if (net == 'host') == is100:
                continue
            sv = dict(flat(ref.get(m) or {})).get(path)
            if pv != sv:
                diffs.append(('%s.%s' % (m, path), pv, sv))
    if verbose:
        print('self-test %s (%s, %s): %.1f s, %d frames-runs; differences against %s:' % (key, net, lat, time.time() - t_start,
                                                                                       len(frags), os.path.basename(sim_metrics_path(key))))
        for d in diffs:
            print('  %-48s protocol %-14s sim %s' % d)
        if not diffs:
            print('  none')
        for n, r in ctx.notes.items():
            if r.get('warn') or any(r.get('k0', {}).values()) or r.get('status') != 'ok':
                print('  run %s: %s k0 %s warn %s' % (n, r.get('status'), r.get('k0'), r.get('warn')))
        if ctx.missing:
            print('  missing fields: %s' % sorted(ctx.missing))
    return out, diffs, ctx


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--selftest' in args:
        args = [a for a in args if a != '--selftest']
        nets = ['host']
        if '--lat100' in args:
            args = [a for a in args if a != '--lat100']
            nets = ['client']
        for k in (args or ['classic']):
            if nets == ['client']:
                _, _, hctx = selftest(k, 'host', verbose=False)
                selftest(k, 'client', shared=hctx.shared)
            else:
                selftest(k, 'host')
    else:
        print(__doc__)
