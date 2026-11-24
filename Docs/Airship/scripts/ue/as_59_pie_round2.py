# as_59_pie_round2.py - round 2 PIE harness, STANDALONE part of the test plan (Docs/Airship/round2/SPEC_A.md section 4):
# one player on L_AirshipTest, fixed 30 fps game time, a frame-by-frame state machine (Slate post-tick callback) armed
# from the inbox like as_43 / as_45 / as_50; it returns at once and the world ticks between inbox calls.
# Run (L_AirshipTest open, no PIE, the round-2 C++ built and as_51..as_57 run):
#   Docs/Airship/scripts/harness/inbox.sh 59 Docs/Airship/scripts/ue/as_59_pie_round2.py 60
#   status: inbox.sh 59s Docs/Airship/scripts/ue/as_59s_status.py 30     stop: inbox.sh 59x Docs/Airship/scripts/ue/as_59x_stop.py 30
# Results: Saved/Airship/round2/r2_result.json (checks with the measured values, events, 10 Hz series), r2_report.txt,
#   r2_log.txt, r2_status.txt; captures Saved/Airship/captures/round2/.
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, LevelEditorPlaySettings Standalone / 1 player,
# UBurrowerSettings.bEnabled False, the UAirshipSettings values the run changes (Settings.MuzzleFXMaxSeconds for T1.2).
# TEMP_AS59_Capture (SceneCapture2D) and TEMP_AS59_SplashPost (a 2 x 2 x 4 m cube on the start platform, the wall of the
# splash test) are placed in the editor level before PIE and removed after it; the map is never saved. The user's own
# Play ("Repeating last play command" in the log) is never stopped. The ships' wind sway is off for the run (as as_43).
# Scheme: Point & Fly (AS59_SCHEME, default 3) unless a phase says otherwise: the cannon aim phases t1_port .. t2_lead fly
# AS59_AIM_SCHEME (default 0, Classic: no scheme logic turns the hull while the harness points the camera; Point & Fly's
# gun lock swings a ship toward a broadside), the drift phases run AS59_DRIFT_SCHEMES (default (3, 1, 0): Point & Fly,
# Galleon, Classic). AS59_ONLY = ('t9_', 't3_') runs settle / spawn2 / board plus the phases whose names start so.
# AS59_* knobs are read from the inbox globals at arm time (they last for the editor session: reset what you set).
#
# Phases (game seconds) -> checks (spec test IDs; "S" variants of listen-server tests where one player can stand in):
#  settle 3     wind off, scheme, Telemetry cmd             T6.1 (S) turrets at the mounts, 400 health; GE gun value
#  spawn2 3     Aura.Airship.Spawn, ship 2 parked far away (the damage dummy and the test balls' source ship)
#  board 2.5    Aura.Airship.Board 0
#  t1_port 5    ship 150 m from the port wall, aim at it      T1.1 muzzle components >= 2 at +0.3 s, 0 at +1.5 s; T1.3
#               (camera), port broadside                     captures +0.3 / +1.2 s; T2.1 ball radius / mesh scale /
#                                                            gravity / launch speed; T2.2 impact within 3 m, apex >= 2 m
#  t1_cap0 3.5  Settings.MuzzleFXMaxSeconds 0, stbd broadside T1.2 0 components at +1.2 s (the asset fix alone)
#  t2_ray 3     a test ball parked on the camera ray          T2.9 the cannons' aim targets don't move (< 0.3 deg)
#  t2_far 7.5   ship 300 m from the port wall's back face     T2.4 elevation at the 8.5 deg cap, the ball lands short
#  t2_lead 6    30 m/s along +X, aim 15 m ahead of the beam   T2.3 impact within 6 m (velocity lead)
#  t4_crew 2.5  Aura.Airship.Damage 100 with the pilot aboard T4.1 (S) pilot -25
#  t9_rest 32   F exit at rest                                T4.4 (S) health kept at exit; T9.3 Hold, < 0.5 m in 30 s
#  t5_cannon 5.5 Mount 0 2 (R1), StationFire twice, Board, Dismount  T5.9 / T5.14 / T5.4 / T5.10 / T5.8 (S)
#  t6_hit 4     ship 2 60 m ahead, TurretFire 1 s             T6.4 ship 2 -80 +-25 %; T6.8 per bullet = 4 x the GE value
#  t6_turret 3  TurretFire 1 s at ship 2's port turret        T6.9 that turret loses health in whole bullets although the
#                                                            line meets ship 2's hull first (its Visibility on)
#  t6_own 3.5   rider on the forward deck, TurretFire at it   T6.5 rider and ship unchanged
#  t5_turret 10 Mount 0 4 (TurretL), StationFire 1 s, 3.5 s   T5.6 / T5.7 (S) 9-11 shots, heat ~0.33, overheat ~3 s
#  t6_destroy 3.5 TurretDamage 0 400 with the gunner on it    T6.6 (S) wreck, fire FX, gunner ejected, no more shots
#  t3_bullets 7 Aura.MechSentinel.TestBullet x3               T3.1 hull -3 (Mesh collision off), T3.2 turret -3, ship
#                                                            unchanged (a real line from outboard: it meets the hull
#                                                            first, the redirect hands it to the turret), T3.3 on-foot -3
#  t2_gun 11    a test ball (ship 2's) 1 m off ship 1's hull, the player shoots it with GA_GunShoot
#                                                            T2.6 -1 per hit, shot down after 30, no splash
#  t2_splash 4  a test ball (ship 2's) into TEMP_AS59_SplashPost, the player 5.5 m from the impact
#                                                            T2.5 (character dummy) 60 x lerp(1, 0.3, d / 600) +-15 %
#  t9_drift_<s> 41 per scheme: 48 m/s, F exit                 T9.1 / T9.2 Drift, 2.5 +-0.3 m/s by 30 s, heading within
#                                                            2 deg, no reverse; T9.5 board while drifting: None, throttle
#  t9_wall 25   drifting at the port wall                     T9.4 stops >= 0.5 m short or on contact, no damage, Hold
#  t9_input 26  Aura.Airship.Input 1 0, then InputClear       T9.6 None while active, Coast, Hold below 3 m/s
#  t7_caps 4    pilot at the helm                             T7.2 wheel 136-144 cm (part_bounds.json) + captures; T7.3
#  t5_kill 3    gunner on R2, ship 1 killed (crew share 0     T5.11 (S) gunner ejected alive
#               for the phase: D4 would give him 25 % of the whole health and kill him)
#  t4_kill 5    pilot of ship 2 at 10 health, Damage 100      T4.2 (S) pilot ejected, then dead; ship alive
#  t5_dead 12   the respawned player mans R1 of ship 2, killed T5.15 (S) the ragdoll ignores the hull (no kick: hull spin
#               there (the ragdoll starts inside the hull)     and speed unchanged), body not thrown up, station free
#  end          log scan                                      T10.1 every new console command ran and logged
# Not here (listen server or not in L_AirshipTest): T2.7, T2.8, T3.4, T3.5, T4.3, T4.5, T5.1-T5.5, T5.12, T5.13, T6.2,
# T6.3, T6.7, T7.1 (Blender), T8.1, T9.7; they are listed as SKIP in the report with the reason.
import json, math, os, time, traceback  # unreal = inbox namespace

AS59_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as59_src = open(AS59_AS30).read()
exec(compile(_as59_src[:_as59_src.index('\nclass AsRun')], AS59_AS30, 'exec'), globals())   # OUT, MAP_NAME, v3, r, dist, tl_get/tl_set, gp, valid, find_log

AS59_VERSION = 'as_59_pie_round2 2026-11-25'
R2DIR = os.path.join(OUT, 'round2')
CAPS2 = os.path.join(OUT, 'captures', 'round2')
TEMP59 = 'TEMP_AS59_'
IA = '/Game/Assets/MyShip/Drivable/Input/'
IA_LMB_PATH = '/Game/Level/PlayerInput/IA_LMB'
SETTINGS_CLS = '/Script/Aura.AirshipSettings'
BALL_BP = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C'
GE_GUN = '/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C'
PART_BOUNDS = os.path.join(OUT, 'part_bounds.json')
MAX_CAPS = 24
# L_AirshipTest (as_22_test_map.py): ship spawn, cannon walls (60 x 4 x 30 m, x -3000..3000, z 100..3100), platform
SPAWN = (0.0, 2500.0, 1600.0)
PORT_FACE_Y, PORT_BACK_Y, STBD_FACE_Y = -9300.0, -9700.0, 14300.0
PARK2 = (0.0, 40000.0, 1600.0)                   # ship 2 parked away from every flight path
S1_T6 = (-10780.0, 40000.0, 1600.0)              # ship 1 for the turret test: its turret muzzles ~60 m behind ship 2's stern
WALL_START = (0.0, -4700.0, 1600.0)              # T9.4: yaw -90 (bow toward the port wall face), ~20 m off it
POST_LOC, POST_SCALE = (-3500.0, -3500.0, 200.0), (2.0, 2.0, 4.0)
POST_FACE_Y = POST_LOC[1] - 100.0 * POST_SCALE[1] / 2.0
CHAR_FOOT = (-2500.0, -2500.0, 150.0)            # the PlayerStart area on the start platform
DRIFT_EXIT_CMS = 4800.0
SCHEME_NAMES = {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}
CMDS_T10 = ['Aura.Airship.Mount', 'Aura.Airship.Dismount', 'Aura.Airship.TurretFire', 'Aura.Airship.TurretDamage',
            'Aura.Airship.StationFire', 'Aura.Airship.Set', 'Aura.Airship.Telemetry', 'Aura.MechSentinel.TestBullet']
SKIPPED = {'T2.7': 'listen server (client copy of a shot-down ball)', 'T2.8': 'needs a rider, a gunner and a pilot (3 players)',
           'T3.4': 'L_AirshipTest has no untagged GAS enemy', 'T3.5': 'L_AirshipTest has no swarm spawner',
           'T4.3': 'listen server (a second player as gunner at 10 health)', 'T4.5': 'needs ship 2 piloted (2 players)',
           'T5.1-T5.5': 'listen server (client F / aim / LMB / broadside)', 'T5.12': 'listen server', 'T5.13': 'listen server',
           'T6.2': 'listen server (client pilot LMB in the bow arc)', 'T6.3': 'listen server', 'T6.7': 'no swarm in L_AirshipTest',
           'T7.1': 'Blender (rig_all.sh / verify_all.sh)', 'T8.1': 'listen server', 'T9.7': 'listen server'}


def en(x):
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


def same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def parse_export(txt):
    """'(A=1.0,B=(0.1,0.2),C=True)' -> dict; nested parentheses (arrays) become lists of floats (or strings)."""
    s = txt.strip()
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    parts, depth, cur, q = [], 0, '', False
    for ch in s:
        if ch == '"':
            q = not q
        if not q and ch == '(':
            depth += 1
        elif not q and ch == ')':
            depth -= 1
        if ch == ',' and depth == 0 and not q:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        parts.append(cur)

    def conv(v):
        v = v.strip()
        if v in ('True', 'False'):
            return v == 'True'
        if v.startswith('(') and v.endswith(')'):
            inner = v[1:-1].strip()
            return [conv(x) for x in inner.split(',')] if inner else []
        try:
            return float(v)
        except ValueError:
            return v
    out = {}
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            out[k.strip()] = conv(v)
    return out


def call(obj, *names, **kw):
    """the first method of obj that exists among names, called with kw['args']."""
    args = kw.get('args', ())
    for n in names:
        f = getattr(obj, n, None)
        if f is not None:
            return f(*args)
    raise AttributeError('none of %s on %s' % (names, obj))


def hit_info(res):
    """(blocking, impact point list, actor, component) of a line trace result (HitResult, tuple or None)."""
    if res is None:
        return False, None, None, None
    hit = res
    if isinstance(res, tuple):
        hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
        if hit is None:
            return False, None, None, None
    try:
        t = unreal.GameplayStatics.break_hit_result(hit)
    except Exception:  # noqa: BLE001
        return False, None, None, None
    bools = [x for x in t if isinstance(x, bool)]
    vecs = [x for x in t if isinstance(x, unreal.Vector)]
    act = next((x for x in t if isinstance(x, unreal.Actor)), None)
    comp = next((x for x in t if isinstance(x, unreal.PrimitiveComponent)), None)
    imp = v3(vecs[1]) if len(vecs) > 1 else (v3(vecs[0]) if vecs else None)
    return (bools[0] if bools else False), imp, act, comp


def mean(xs):
    return sum(xs) / len(xs) if xs else None


class R2Run(object):
    def __init__(self):
        self.R = {'version': AS59_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': {},
                  'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'balls': {}, 'done': False, 'setup': {}}
        self.orig = {}
        self.handle = None
        self.phase = 'arming'
        self.phases = []
        self.pi = -1
        self.p_t0 = 0.0
        self.now = 0.0
        self.t_world0 = None
        self.wall0 = time.time()
        self.last_sample = -1.0
        self.last_write = 0.0
        self.D = {}
        self.w = self.pc = self.char = self.ship = self.ship2 = self.sub = None
        self.cap = None
        self.cap_dead = False
        self.ncap = 0
        self.balls = {}
        self.log_file = find_log()
        self.log_off = os.path.getsize(self.log_file) if self.log_file else 0
        self.user_play = False
        self.frames = 0
        self.act = {}
        self.local = {}
        self.cmds_run = []
        self.attrs = {}
        for n in ('Health', 'MaxHealth'):
            a = unreal.GameplayAttribute()
            a.import_text('(AttributeName="%s",Attribute=/Script/Aura.MyAttributeSet:%s,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")' % (n, n))
            self.attrs[n] = a

    # ---------------------------------------------------------------- output
    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.phase, msg)
        self.R['lines'].append(s)
        try:
            with open(os.path.join(R2DIR, 'r2_log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def check(self, key, status, msg, data=None):
        self.R['checks'][key] = {'status': status, 'summary': msg, 'data': data, 't': r(self.now), 'phase': self.phase}
        self.line(status, '%s: %s' % (key, msg))

    def event(self, name, **kw):
        kw.update({'event': name, 't': r(self.now), 'phase': self.phase})
        self.R['events'].append(kw)

    def err(self, where):
        e = self.R['errors'].setdefault(where, {'n': 0, 'last': ''})
        e['n'] += 1
        e['last'] = traceback.format_exc()[-1500:]
        if e['n'] == 1:
            self.line('WARN', 'script error in %s: %s' % (where, e['last'].strip().splitlines()[-1]))

    def status_text(self):
        c = {}
        for v in self.R['checks'].values():
            c[v['status']] = c.get(v['status'], 0) + 1
        left = sum(d for _, d in self.phases[self.pi + 1:]) if self.phases and self.pi >= 0 else None
        return 'as_59 phase %s (%d/%d) game_t %.1f wall %.0f s frames %d checks %s, about %s game s left, done %s' % (
            self.phase, self.pi + 1, len(self.phases), self.now, time.time() - self.wall0, self.frames, c,
            None if left is None else int(left), self.R['done'])

    def write(self, force=False):
        if not force and time.time() - self.last_write < 2.0:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        self.R['balls'] = self.balls
        try:
            with open(os.path.join(R2DIR, 'r2_result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
            with open(os.path.join(R2DIR, 'r2_status.txt'), 'w') as f:
                f.write(self.status_text() + '\n')
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- arm / restore
    def settings(self):
        return unreal.get_default_object(unreal.load_class(None, SETTINGS_CLS))

    def build_phases(self):
        ph = [('settle', 3.0), ('spawn2', 3.0), ('board', 2.5), ('t1_port', 5.0), ('t1_cap0', 3.5), ('t2_ray', 3.0),
              ('t2_far', 7.5), ('t2_lead', 6.0), ('t4_crew', 2.5), ('t9_rest', 32.0), ('t5_cannon', 5.5), ('t6_hit', 4.0),
              ('t6_turret', 3.0), ('t6_own', 3.5), ('t5_turret', 10.0), ('t6_destroy', 3.5), ('t3_bullets', 7.0), ('t2_gun', 11.0),
              ('t2_splash', 4.0)]
        for s in self.cfg['drift_schemes']:
            ph.append(('t9_drift_%d' % s, 41.0))
        ph += [('t9_wall', 25.0), ('t9_input', 26.0), ('t7_caps', 4.0), ('t5_kill', 3.0), ('t4_kill', 5.0), ('t5_dead', 12.0)]
        only = self.cfg.get('only')
        if only:
            keep = set(['settle', 'spawn2', 'board'] + list(only))
            ph = [p for p in ph if p[0] in keep or any(p[0].startswith(o) for o in only)]
        return ph

    def arm(self):
        os.makedirs(R2DIR, exist_ok=True)
        os.makedirs(CAPS2, exist_ok=True)
        g = globals()
        self.cfg = {'scheme': int(g.get('AS59_SCHEME', 3) or 0), 'aim_scheme': int(g.get('AS59_AIM_SCHEME', 0) or 0),
                    'drift_schemes': tuple(g.get('AS59_DRIFT_SCHEMES') or (3, 1, 0)),
                    'only': tuple(g.get('AS59_ONLY') or ())}
        self.phases = self.build_phases()
        self.R['cfg'] = self.cfg
        self.R['phases'] = self.phases
        with open(os.path.join(R2DIR, 'r2_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (AS59_VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open the map first' % (ew.get_path_name(), MAP_NAME))
            return False
        for cls in ('/Script/Aura.AirshipTurret', '/Script/Aura.AirshipCannonball'):
            if unreal.load_class(None, cls) is None:
                self.line('FAIL', '%s not found: the round-2 C++ is not built into this editor' % cls)
                return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 4 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        try:
            ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
            self.orig['play'] = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
            tl_set(ps, {'PlayNetMode': 'PIE_Standalone', 'PlayNumberOfClients': 1})
            self.line('INFO', 'play settings Standalone / 1 player for the run (were %s)' % self.orig['play'])
        except Exception:  # noqa: BLE001
            self.err('play_settings')
        try:
            bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            self.orig['burrower_enabled'] = bool(bcdo.get_editor_property('bEnabled'))
            bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('burrower_settings')
        try:
            st = self.settings()
            self.orig['settings'] = dict((n, st.get_editor_property(n)) for n in (
                'MuzzleFXMaxSeconds', 'CrewDamageShare', 'TurretGunDamageMultiplier', 'DriverTurretArcDeg', 'DriftSpeed',
                'DriftMinExitSpeed', 'bHoldWhenUnpiloted', 'HoldEngageSpeed', 'bSpawnTurrets'))
            self.R['setup']['settings'] = dict((k, str(v)) for k, v in self.orig['settings'].items())
        except Exception:  # noqa: BLE001
            self.err('settings_snapshot')
        for n in ('IA_AirshipFire', 'IA_AirshipBoard', 'IA_AirshipExit'):
            self.act[n] = unreal.load_asset(IA + n)
        self.act['IA_LMB'] = unreal.load_asset(IA_LMB_PATH)
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP59):
                    eas.destroy_actor(a)
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, -6000, 3000))
            cap.set_actor_label(TEMP59 + 'Capture')
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
            post = eas.spawn_actor_from_object(unreal.load_asset('/Engine/BasicShapes/Cube'), unreal.Vector(*POST_LOC), unreal.Rotator(0, 0, 0))
            post.set_actor_label(TEMP59 + 'SplashPost')
            post.set_actor_scale3d(unreal.Vector(*POST_SCALE))
            smc = post.static_mesh_component
            smc.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
            smc.set_collision_profile_name('BlockAll')
            self.line('INFO', 'placed %sCapture + %sSplashPost in the editor level (removed after PIE, the map is not saved)' % (TEMP59, TEMP59))
        except Exception:  # noqa: BLE001
            self.err('temp_actors')
        with open(os.path.join(R2DIR, 'r2_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed; standalone PIE requested; %d phases, about %d game s' % (len(self.phases), sum(d for _, d in self.phases)))
        return True

    def restore(self):
        try:
            if 'engine' in self.orig:
                eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
                tl_set(eng, {'bUseFixedFrameRate': bool(self.orig['engine'].get('bUseFixedFrameRate', False)),
                             'FixedFrameRate': float(self.orig['engine'].get('FixedFrameRate', 30.0))})
        except Exception:  # noqa: BLE001
            self.err('restore_engine')
        try:
            if 'play' in self.orig:
                ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
                tl_set(ps, {'PlayNetMode': str(self.orig['play'].get('PlayNetMode', 'PIE_Standalone')).split('.')[-1],
                            'PlayNumberOfClients': int(self.orig['play'].get('PlayNumberOfClients', 1))})
        except Exception:  # noqa: BLE001
            self.err('restore_play')
        try:
            if 'burrower_enabled' in self.orig:
                bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
                bcdo.set_editor_property('bEnabled', self.orig['burrower_enabled'], unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_burrower')
        try:
            # Aura.Airship.Set Settings.<Name> writes the mutable class default: put every value the run may change back
            st = self.settings()
            for n, v in (self.orig.get('settings') or {}).items():
                st.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_settings')

    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            n = 0
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP59):
                    eas.destroy_actor(a)
                    n += 1
            self.line('INFO', 'removed %d %s* actors from the editor level' % (n, TEMP59))
        except Exception:  # noqa: BLE001
            self.err('remove_temp')

    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        for s in (self.ship, self.ship2):
            try:
                if valid(s):
                    s.debug_clear_input()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self.w is not None and self.local.get('turret_fire_on'):
                unreal.SystemLibrary.execute_console_command(self.w, 'Aura.Airship.TurretFire 0')
        except Exception:  # noqa: BLE001
            pass
        self.scan_log()
        self.write_skips()
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and not self.user_play:
            les.editor_request_end_play()
        self.phase = 'ending'
        self.end_wall = time.time()

    def end_tick(self):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and time.time() - self.end_wall < 20.0 and not self.user_play:
            return
        self.restore()
        if not les.is_in_play_in_editor():
            self.remove_temp()
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        self.phase = 'finished'
        self.R['done'] = True
        self.write(True)
        write_r2_report(self.R)
        self.line('INFO', 'done; results in round2/r2_result.json / r2_report.txt')

    def write_skips(self):
        for k, why in SKIPPED.items():
            if k not in self.R['checks']:
                self.R['checks'][k] = {'status': 'SKIP', 'summary': why, 'data': None, 't': r(self.now), 'phase': '-'}

    # ---------------------------------------------------------------- log
    def scan_log(self):
        if not self.log_file:
            return
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                txt = f.read()
            lines = txt.splitlines()
            pats = {'airship': 'LogAirship', 'airship_warn': 'LogAirship: Warning', 'error': 'Error:', 'ensure': 'Ensure condition failed',
                    'accessed_none': 'Accessed None', 'user_play': 'Repeating last play command', 'not_recognized': 'Command not recognized',
                    'turret': 'Turret', 'crew': 'crew damage', 'mounted': 'mounted', 'shot_down': 'shot down', 'sentinel': 'MechSentinel'}
            sc = {}
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                sc[k] = {'count': len(hit), 'sample': hit[:10] + (hit[-5:] if len(hit) > 15 else [])}
            self.R['log_scan'] = sc
            if sc['user_play']['count']:
                self.user_play = True
            # T10.1: every new command was recognised and logged something with its name
            res = {}
            for c in CMDS_T10:
                ran = [x for x in self.cmds_run if x.split()[0] == c]
                if not ran:
                    res[c] = 'not run'
                    continue
                nr = [l for l in lines if 'Command not recognized' in l and c in l]
                lg = [l for l in lines if c in l and 'Command not recognized' not in l]
                res[c] = 'ok (%d log lines)' % len(lg) if lg and not nr else ('NOT RECOGNISED' if nr else 'no log line')
            tl = [l for l in lines if 'LogAirship' in l and any(k in l.lower() for k in ('unpiloted', 'station', 'turret'))]
            res['Telemetry line 3'] = 'ok: %s' % tl[0][:160] if tl else 'no telemetry line with unpiloted / station / turret'
            bad = [k for k, v in res.items() if not str(v).startswith('ok')]
            self.check('T10.1_console', 'PASS' if not bad else ('FAIL' if any('NOT RECOGNISED' in str(res[k]) for k in bad) else 'WARN'),
                       'new console commands: %s' % res, res)
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    def scan_user_play(self):
        if not self.log_file or int(self.now * 2) == self.local.get('_ulast'):
            return
        self.local['_ulast'] = int(self.now * 2)
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                if 'Repeating last play command' in f.read():
                    self.user_play = True
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- PIE helpers
    def cmd(self, c):
        unreal.SystemLibrary.execute_console_command(self.w, c)
        self.cmds_run.append(c)
        self.event('cmd', cmd=c)
        self.line('INFO', 'console: %s' % c)

    def subsystem(self):
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and same(lp.get_world(), self.w):
                    return s
            except Exception:  # noqa: BLE001
                pass
        return None

    def inject(self, action, x=1.0):
        try:
            if self.sub is None:
                self.sub = self.subsystem()
            self.sub.inject_input_vector_for_action(self.act[action], unreal.Vector(x, 0.0, 0.0), [], [])
        except Exception:  # noqa: BLE001
            self.err('inject_' + action)

    def tele(self, ship):
        try:
            return parse_export(ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def mode(self, ship):
        try:
            return int(self.tele(ship).get('UnpilotedMode', -1))
        except Exception:  # noqa: BLE001
            return -1

    def health(self, a):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None
            x = asc.get_gameplay_attribute_value(self.attrs['Health'])
            return round(float(x[0] if isinstance(x, tuple) else x), 3)
        except Exception:  # noqa: BLE001
            self.err('health')
            return None

    def hurt(self, a, amount):
        """Damage through the airship damage effect on a's own ASC (SetByCaller), as as_45's settle phase."""
        try:
            ge = unreal.load_class(None, DMG_GE)
            tag = unreal.GameplayTag()
            tag.import_text('(TagName="SetDamageByCaller")')
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            spec = asc.make_outgoing_spec(ge, 1.0, asc.make_effect_context())
            spec = unreal.AbilitySystemLibrary.assign_tag_set_by_caller_magnitude(spec, tag, float(amount))
            asc.apply_gameplay_effect_spec_to_self(spec)
        except Exception:  # noqa: BLE001
            self.err('hurt')

    def hull(self, ship):
        return ship.get_editor_property('HullCollision')

    def teleport(self, ship, loc, yaw=0.0, vel=(0.0, 0.0, 0.0)):
        ship.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
        h = self.hull(ship)
        h.set_physics_linear_velocity(unreal.Vector(*vel), False, 'None')
        h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')

    def wind_off(self, ship):
        try:
            fc = ship.get_editor_property('Flight')
            for n in ('WindLateralAccel', 'WindRollAccel', 'WindPitchAccel'):
                # NEVER: no Pre/PostEditChange on a PIE component (that re-registers it, as_43)
                fc.set_editor_property(n, 0.0, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('wind_off')

    def set_scheme(self, ship, s):
        try:
            ship.set_control_scheme(getattr(unreal.AirshipControlScheme, SCHEME_NAMES[int(s)]))
        except Exception:  # noqa: BLE001
            self.err('set_scheme')

    def pawn(self):
        try:
            return self.pc.get_controlled_pawn()
        except Exception:  # noqa: BLE001
            return None

    def char_info(self, c, ship=None):
        if not valid(c):
            return None
        cm = gp(c, 'character_movement', 'CharacterMovement')
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        par = c.get_attach_parent_actor()
        d = {'loc': r(v3(c.get_actor_location()), 1), 'mode': en(cm.get_editor_property('movement_mode')) if cm else None,
             'cmc_tick': bool(cm.is_component_tick_enabled()) if cm else None, 'coll': en(caps.get_collision_enabled()) if caps else None,
             'actor_coll': bool(c.get_actor_enable_collision()), 'att': par.get_name() if par else None, 'health': self.health(c)}
        if valid(ship):
            try:
                d['rider'] = c.get_name() in [p.get_name() for p in ship.get_passengers()]
            except Exception:  # noqa: BLE001
                d['rider'] = None
        return d

    def tp_char(self, loc, yaw=0.0):
        try:
            if valid(self.char) and self.char.get_attach_parent_actor() is None:
                self.char.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
                cm = gp(self.char, 'character_movement', 'CharacterMovement')
                if cm:
                    cm.stop_movement_immediately()
        except Exception:  # noqa: BLE001
            self.err('tp_char')

    def deck_point(self, ship, hx, hy):
        """world point on top of the hull's collision at hull-space (hx, hy), plus the character's half height."""
        tr = ship.get_actor_transform()
        top = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, 1600.0))
        bot = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, -200.0))
        res = self.hull(ship).line_trace_component(top, bot, False, False, False)
        hit = None
        if isinstance(res, tuple):
            if not (isinstance(res[0], bool) and not res[0]):
                hit = next((v3(x) for x in res if isinstance(x, unreal.Vector)), None)
        caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
        hh = caps.get_scaled_capsule_half_height() if caps else 90.0
        p = hit if hit is not None else v3(unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, 700.0)))
        return [p[0], p[1], p[2] + hh + 30.0], hit is not None

    def local_socket(self, ship, name):
        """component-space (= hull-space) location of a mesh bone / socket."""
        m = ship.get_editor_property('Mesh')
        return v3(m.get_socket_transform(name, unreal.RelativeTransformSpace.RTS_COMPONENT).translation)

    def world_of(self, ship, local):
        return v3(unreal.MathLibrary.transform_location(ship.get_actor_transform(), unreal.Vector(*local)))

    def muzzle_comps(self, ship):
        out = []
        try:
            fx = ship.get_editor_property('MuzzleFX')
            for c in ship.get_editor_property('Mesh').get_children_components(True):
                if isinstance(c, unreal.NiagaraComponent) and fx is not None and same(c.get_asset(), fx):
                    out.append(c.get_name())
        except Exception:  # noqa: BLE001
            self.err('muzzle')
        return out

    def turrets(self, ship):
        try:
            return [t for t in (ship.get_editor_property('Turrets') or []) if valid(t)]
        except Exception:  # noqa: BLE001
            self.err('turrets')
            return []

    def tstate(self, t):
        d = {}
        for k, names in (('destroyed', ('is_turret_destroyed',)), ('heat', ('get_heat01', 'get_heat_01')), ('overheated', ('is_overheated',)),
                         ('health', ('get_health',)), ('shots', ('get_shot_count',))):
            try:
                v = call(t, *names)
                d[k] = round(float(v), 4) if isinstance(v, float) else v
            except Exception:  # noqa: BLE001
                d[k] = None
        return d

    def gunner(self, ship, s):
        try:
            return call(ship, 'get_station_gunner', args=(s,))
        except Exception:  # noqa: BLE001
            try:
                return (ship.get_editor_property('StationGunners') or [None] * 6)[s]
            except Exception:  # noqa: BLE001
                return None

    def anim(self, ship, names):
        out = {}
        try:
            ai = ship.get_editor_property('Mesh').get_anim_instance()
        except Exception:  # noqa: BLE001
            return out
        for n in names:
            try:
                out[n] = round(float(ai.get_editor_property(n)), 3)
            except Exception:  # noqa: BLE001
                out[n] = None
        return out

    def cam(self):
        cm = unreal.GameplayStatics.get_player_camera_manager(self.w, 0)
        return cm.get_camera_location(), cm.get_camera_rotation()

    def aim_at(self, point):
        try:
            loc, _ = self.cam()
            self.pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(*point)))
        except Exception:  # noqa: BLE001
            self.err('aim_at')

    def cam_ray(self, dist_cm=60000.0, ignore=None):
        """first Visibility hit on the camera's centre ray (what the aim traces see), Python side."""
        try:
            loc, rot = self.cam()
            fwd = unreal.MathLibrary.get_forward_vector(rot)
            end = loc + fwd * dist_cm
            res = unreal.SystemLibrary.line_trace_single(self.w, loc, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False,
                                                         ignore or [], unreal.DrawDebugTrace.NONE, True)
            return hit_info(res)
        except Exception:  # noqa: BLE001
            self.err('cam_ray')
            return False, None, None, None

    def trace(self, a, b, ignore=None):
        try:
            res = unreal.SystemLibrary.line_trace_single(self.w, unreal.Vector(*a), unreal.Vector(*b), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, ignore or [], unreal.DrawDebugTrace.NONE, True)
            ok, imp, act, comp = hit_info(res)
            return {'hit': ok, 'at': r(imp, 1) if imp else None, 'actor': act.get_name() if act else None,
                    'comp': comp.get_name() if comp else None}
        except Exception:  # noqa: BLE001
            self.err('trace')
            return None

    def fire_side(self, side):
        """the pilot's broadside: IA_AirshipFire injected (RequestFire on the camera's side), fallback in ph_* after 0.6 s."""
        self.D['fire_t'] = self.now
        self.D['side'] = side
        self.D['mz_old'] = set(self.muzzle_comps(self.ship))
        self.D['nb0'] = len(self.balls)
        self.inject('IA_AirshipFire')
        self.event('inject', what='IA_AirshipFire (%s)' % side)

    def fire_fallback(self):
        ft = self.D.get('fire_t')
        if ft is not None and self.now - ft >= 0.6 and not self.D.get('fb') and len(self.balls) == self.D.get('nb0'):
            self.D['fb'] = True
            try:
                self.ship.request_fire()
            except Exception:  # noqa: BLE001
                self.err('request_fire')
            self.line('WARN', 'the fire injection made no ball in 0.6 s: fallback RequestFire')

    def spawn_ball(self, loc, vel, source, damage=60.0, gravity=-1.0):
        try:
            cls = unreal.load_class(None, BALL_BP) or unreal.load_class(None, BALL_CLS)
            b = unreal.AirshipCannonball.spawn_test_cannonball(self.w, cls, unreal.Vector(*loc), unreal.Vector(*vel), source, float(damage), float(gravity))
            self.event('test_ball', loc=r(list(loc), 0), vel=r(list(vel), 0), source=source.get_name() if source else None)
            return b
        except Exception:  # noqa: BLE001
            self.err('spawn_ball')
            return None

    def ball_state(self, b):
        d = {}
        for k, names in (('health', ('get_ball_health',)), ('max', ('get_ball_max_health',)), ('shot_down', ('is_shot_down',))):
            try:
                d[k] = call(b, *names)
            except Exception:  # noqa: BLE001
                d[k] = None
        return d

    # ---------------------------------------------------------------- balls
    def track_balls(self):
        """every cannonball of the world: first sight (position, velocity, radius, mesh scale, gravity), path samples, where
        it stopped or went hidden (the impact), shot down, gone."""
        try:
            seen = set()
            for b in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, BALL_CLS)):
                k = b.get_name()
                seen.add(k)
                p = v3(b.get_actor_location())
                rec = self.balls.get(k)
                if rec is None:
                    rec = {'first': r(p, 1), 'v0': r(v3(b.get_velocity()), 1), 't0': r(self.now, 3), 'phase': self.phase, 'path': []}
                    try:
                        rec['radius'] = round(b.get_editor_property('CollisionSphere').get_scaled_sphere_radius(), 2)
                        bm = b.get_editor_property('BallMesh')
                        sc = call(bm, 'get_world_scale', 'get_component_scale')
                        rec['mesh_scale'] = r(v3(sc), 3)
                        rec['gravity'] = round(float(b.get_editor_property('Movement').get_editor_property('projectile_gravity_scale')), 3)
                        src = b.get_editor_property('SourceShip')
                        rec['source'] = src.get_name() if src else None
                        rec['ship_v'] = r(v3(src.get_velocity()), 1) if src else None
                    except Exception:  # noqa: BLE001
                        self.err('ball_first')
                    self.balls[k] = rec
                if len(rec['path']) < 400 and not rec.get('stopped'):
                    rec['path'].append([r(self.now, 3)] + r(p, 1))
                hidden = bool(gp(b, 'hidden', 'bHidden', default=False))
                if hidden and 'hidden_at' not in rec:
                    rec['hidden_at'], rec['t_hidden'] = r(p, 1), r(self.now, 3)
                st = self.ball_state(b)
                if st.get('shot_down') and 'shot_down_t' not in rec:
                    rec['shot_down_t'], rec['shot_down_at'] = r(self.now, 3), r(p, 1)
                if rec.get('stopped'):
                    continue
                if rec.get('last') is not None and dist(p, rec['last']) < 2.0 and self.now > rec['t_last'] + 1e-6:
                    if dist(p, rec['first']) > 50.0 or hidden:
                        rec['stopped'], rec['t_hit'], rec['impact'] = True, rec['t_last'], r(p, 1)
                else:
                    rec['last'], rec['t_last'] = r(p, 1), self.now
            for k, rec in self.balls.items():
                if k not in seen and not rec.get('gone'):
                    rec['gone'] = r(self.now, 3)
                    if 'impact' not in rec and rec.get('last') is not None:
                        rec['impact'] = rec['last']
        except Exception:  # noqa: BLE001
            self.err('balls')

    def balls_since(self, t0, phase=None):
        return [(k, b) for k, b in self.balls.items() if b['t0'] >= t0 - 1e-3 and (phase is None or b['phase'] == phase)]

    def impact_of(self, b):
        return b.get('hidden_at') or b.get('impact')

    def apex_above_line(self, b):
        """highest point of the path above the straight line from the first sample to the impact (cm)."""
        imp = self.impact_of(b)
        if not imp or len(b['path']) < 3:
            return None
        p0 = b['path'][0][1:]
        dx, dy = imp[0] - p0[0], imp[1] - p0[1]
        L = math.hypot(dx, dy)
        if L < 1.0:
            return None
        best = -1e9
        for s in b['path']:
            f = ((s[1] - p0[0]) * dx + (s[2] - p0[1]) * dy) / (L * L)
            if 0.0 <= f <= 1.0:
                best = max(best, s[3] - (p0[2] + f * (imp[2] - p0[2])))
        return round(best, 1)

    # ---------------------------------------------------------------- captures
    def capture(self, label, kind, ship=None):
        if self.cap_dead or self.ncap >= MAX_CAPS:
            return None
        try:
            if self.cap is None:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.SceneCapture2D)
                        if (TEMP59 + 'Capture') in a.get_actor_label()]
                if not caps:
                    self.cap_dead = True
                    self.line('WARN', 'no %sCapture in the PIE world: no captures' % TEMP59)
                    return None
                rt = unreal.RenderingLibrary.create_render_target2d(self.w, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = caps[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.cap = (caps[0], cc, rt)
            a, cc, rt = self.cap
            fov = 60.0
            if kind == 'player':
                cm = unreal.GameplayStatics.get_player_camera_manager(self.w, 0)
                frm, rot, fov = cm.get_camera_location(), cm.get_camera_rotation(), cm.get_fov_angle()
            else:
                tr = ship.get_actor_transform()
                at = lambda x, y, z: unreal.MathLibrary.transform_location(tr, unreal.Vector(x, y, z))  # noqa: E731
                views = {'port': ((-3200.0, -2600.0, 900.0), (-600.0, -650.0, 300.0)),
                         'stbd': ((-3200.0, 2600.0, 900.0), (-600.0, 650.0, 300.0)),
                         'helm': ((-650.0, -1500.0, 500.0), (-700.0, 0.0, 330.0)),
                         'top': ((0.0, 0.0, 7500.0), (0.0, 0.0, 300.0)),
                         'bow': ((1200.0, -1400.0, 1300.0), (2300.0, 0.0, 700.0))}
                if kind not in views:
                    return None
                frm, to = at(*views[kind][0]), at(*views[kind][1])
                rot = unreal.MathLibrary.find_look_at_rotation(frm, to)
                fov = 75.0 if kind == 'top' else 55.0
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(frm, rot, False, True)
            cc.capture_scene()
            name = '%s_%s' % (label, kind)
            unreal.RenderingLibrary.export_render_target(self.w, rt, CAPS2, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 't': r(self.now), 'file': os.path.join(CAPS2, name + '.png')})
            return name
        except Exception:  # noqa: BLE001
            self.err('capture')
            self.cap_dead = True
            return None

    # ---------------------------------------------------------------- sampling
    def sample(self):
        if self.now - self.last_sample < 0.1:
            return
        self.last_sample = self.now
        try:
            s = {'t': r(self.now, 2), 'ph': self.phase}
            for key, ship in (('S1', self.ship), ('S2', self.ship2)):
                if valid(ship):
                    t = self.tele(ship)
                    s[key] = {'loc': r(v3(ship.get_actor_location()), 0), 'yaw': r(ship.get_actor_rotation().yaw, 2),
                              'v': r(t.get('SpeedMS'), 2), 'vf': r(t.get('ForwardSpeedMS'), 2), 'hp': r(t.get('Health'), 1),
                              'mode': t.get('UnpilotedMode'), 'stations': t.get('StationMask'), 'pilot_hp': t.get('PilotHealth'),
                              'heat': t.get('TurretHeat'), 'thr': r(t.get('Throttle'), 2)}
            if valid(self.char):
                s['C'] = {'loc': r(v3(self.char.get_actor_location()), 0), 'hp': self.health(self.char),
                          'att': self.char.get_attach_parent_actor().get_name() if self.char.get_attach_parent_actor() else None}
            self.R['series'].append(s)
        except Exception:  # noqa: BLE001
            self.err('sample')

    # ---------------------------------------------------------------- state machine
    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if sum(e['n'] for e in self.R['errors'].values()) > 400:
                self.finish('too many script errors')
        self.write()

    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'wait_pie':
            ws = [w for w in unreal.EditorLevelLibrary.get_pie_worlds(False) if MAP_NAME in w.get_path_name()]
            if ws:
                self.w = ws[0]
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE world %s' % self.w.get_path_name())
            elif time.time() - self.wall0 > 240:
                self.finish('PIE did not start in 240 s')
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        tw = unreal.GameplayStatics.get_time_seconds(self.w)
        if self.t_world0 is None:
            self.t_world0 = tw
        self.now = tw - self.t_world0
        self.frames += 1
        if self.phase == 'wait_actors':
            if self.find_actors():
                self.next_phase()
            elif self.now > 30:
                self.finish('actors not found after 30 s: %s' % self.R.get('setup_try'))
            return
        self.scan_user_play()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        self.track_balls()
        self.sample()
        el = self.now - self.p_t0
        ph = self.phase
        base = 't9_drift' if ph.startswith('t9_drift_') else ph
        try:
            getattr(self, 'ph_' + base, lambda e: None)(el)
        except Exception:  # noqa: BLE001
            self.err('ph_' + ph)
        if el >= self.phases[self.pi][1]:
            try:
                getattr(self, 'end_' + base, lambda: None)()
            except Exception:  # noqa: BLE001
                self.err('end_' + ph)
                self.check(ph, 'FAIL', 'evaluation crashed: %s' % traceback.format_exc().strip().splitlines()[-1])
            self.write(True)
            self.next_phase()

    def next_phase(self):
        self.pi += 1
        if self.pi >= len(self.phases):
            self.finish('all phases done')
            return
        self.phase = self.phases[self.pi][0]
        self.p_t0 = self.now
        self.D = {}
        if self.phase.startswith('t9_drift_'):
            self.D['scheme'] = int(self.phase.rsplit('_', 1)[1])
        self.line('INFO', 'phase %s (%.0f s)' % (self.phase, self.phases[self.pi][1]))
        base = 't9_drift' if self.phase.startswith('t9_drift_') else self.phase
        try:
            getattr(self, 'start_' + base, lambda: None)()
        except Exception:  # noqa: BLE001
            self.err('start_' + self.phase)

    def find_actors(self):
        try:
            ship_cls = unreal.load_class(None, SHIP_CLS)
            self.pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
            self.char = self.pc.get_controlled_pawn() if self.pc else None
            ss = unreal.GameplayStatics.get_all_actors_of_class(self.w, ship_cls)
            self.ship = ss[0] if ss else None
            self.sub = self.subsystem()
            self.R['setup_try'] = {'pc': bool(self.pc), 'char': bool(self.char), 'ship': bool(self.ship), 'sub': bool(self.sub)}
            if all(self.R['setup_try'].values()) and isinstance(self.char, unreal.Character):
                self.R['setup'].update({'world': self.w.get_path_name(), 'char': self.char.get_name(), 'ship': self.ship.get_name(),
                                        'char_loc': r(v3(self.char.get_actor_location()), 0), 'ship_loc': r(v3(self.ship.get_actor_location()), 0)})
                self.line('INFO', 'setup %s' % self.R['setup'])
                return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
        return False

    # ================================================================ phases
    # ---- settle: wind off, scheme, cannon / turret geometry, the gun's damage value
    def start_settle(self):
        self.wind_off(self.ship)
        self.set_scheme(self.ship, self.cfg['scheme'])
        self.R['setup']['scheme'] = SCHEME_NAMES.get(self.cfg['scheme'])
        geo = {}
        for c in ('L1', 'L2', 'R1', 'R2'):
            try:
                geo[c] = r(self.local_socket(self.ship, 'Cannon_%s_Muzzle' % c), 1)
            except Exception:  # noqa: BLE001
                self.err('muzzle_socket')
        self.geo = geo
        self.R['setup']['muzzles_hull'] = geo
        try:
            ge = unreal.load_class(None, GE_GUN)
            cdo = unreal.get_default_object(ge)
            tot = 0.0
            for m in cdo.get_editor_property('modifiers'):
                mm = m.get_editor_property('modifier_magnitude').get_editor_property('scalable_float_magnitude')
                tot += float(mm.get_editor_property('value'))
            self.gun_base = tot
        except Exception:  # noqa: BLE001
            self.err('ge_gun')
            self.gun_base = 1.0
        if not self.gun_base or self.gun_base <= 0.0:
            # not a plain scalable float (SetByCaller, attribute based): the turret falls back to GunDamageFallback (1)
            self.line('WARN', 'GE_GunShootDamage magnitude not readable as a plain number (%s): expecting the fallback 1' % self.gun_base)
            self.gun_base = 1.0
        self.R['setup']['gun_base_damage'] = self.gun_base
        self.line('INFO', 'muzzles (hull space) %s; GE_GunShootDamage magnitude %.3f' % (geo, self.gun_base))

    def ph_settle(self, el):
        if el >= 1.0 and 'tl' not in self.D:
            self.D['tl'] = True
            self.cmd('Aura.Airship.Telemetry')

    def end_settle(self):
        ts = self.turrets(self.ship)
        st = self.settings()
        mounts = []
        try:
            for m in st.get_editor_property('TurretMounts'):
                mounts.append(v3(m.get_editor_property('location')))
        except Exception:  # noqa: BLE001
            self.err('mounts')
        tr = self.ship.get_actor_transform()
        out = []
        ok = len(ts) == 2
        for t in ts:
            idx = call(t, 'get_turret_index') if hasattr(t, 'get_turret_index') else None
            loc = v3(unreal.MathLibrary.inverse_transform_location(tr, t.get_actor_location()))
            want = mounts[idx] if isinstance(idx, int) and idx < len(mounts) else None
            d = dist(loc, want) if want else None
            par = t.get_attach_parent_actor()
            hp = self.tstate(t).get('health')
            out.append({'turret': t.get_name(), 'index': idx, 'hull_loc': r(loc, 2), 'mount': want, 'off_cm': r(d, 2) if d is not None else None,
                        'parent': par.get_name() if par else None, 'health': hp, 'class': t.get_class().get_name()})
            ok = ok and d is not None and d <= 1.0 and same(par, self.ship) and hp is not None and abs(hp - 400.0) < 0.5
        self.check('T6.1_turrets_S', 'PASS' if ok else 'FAIL', 'ship 1 has %d turrets (want 2) at the mounts +-1 cm, attached, 400 health: %s'
                   % (len(ts), out), out)

    # ---- ship 2: the damage dummy and the test balls' source ship
    def start_spawn2(self):
        self.D['before'] = set(a.get_name() for a in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, SHIP_CLS)))
        self.cmd('Aura.Airship.Spawn')

    def ph_spawn2(self, el):
        if self.ship2 is None:
            for a in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, SHIP_CLS)):
                if a.get_name() not in self.D['before']:
                    self.ship2 = a
                    self.line('INFO', 'ship 2: %s' % a.get_name())
        if self.ship2 is not None and el >= 1.0 and 'parked' not in self.D:
            self.D['parked'] = True
            self.wind_off(self.ship2)
            self.teleport(self.ship2, PARK2, 0.0)

    def end_spawn2(self):
        self.check('setup_ship2', 'PASS' if valid(self.ship2) else 'FAIL', 'ship 2 spawned and parked at %s: %s' % (
            PARK2, self.ship2.get_name() if valid(self.ship2) else None))

    # ---- board
    def start_board(self):
        self.cmd('Aura.Airship.Board 0')

    def end_board(self):
        ok = same(self.pawn(), self.ship) and same(self.ship.get_pilot(), self.char)
        self.check('setup_board', 'PASS' if ok else 'FAIL', 'player 0 at the helm of ship 1: %s' % ok)

    # ---- T1.1 / T1.3 / T2.1 / T2.2: port broadside 150 m from the wall
    def port_target(self, dist_cm, face_y):
        l1, l2 = self.geo['L1'], self.geo['L2']
        ship_y = face_y + dist_cm - 0.5 * (l1[1] + l2[1])
        return ship_y, [0.5 * (l1[0] + l2[0]), face_y, SPAWN[2] + 0.5 * (l1[2] + l2[2])]

    def start_t1_port(self):
        # the cannon aim phases (t1_port .. t2_lead) fly AS59_AIM_SCHEME (default 0, Classic): no scheme logic turns the hull
        # while the harness points the camera (Point & Fly's gun lock swings a ship toward a broadside); the ballistic aim
        # is the same in every scheme
        self.set_scheme(self.ship, self.cfg['aim_scheme'])
        y, A = self.port_target(15000.0, PORT_FACE_Y)
        self.teleport(self.ship, (SPAWN[0], y, SPAWN[2]), 0.0)
        self.D['A'] = A
        self.line('INFO', 'ship 1 at y %.0f: port muzzles 150 m from the wall face; aim point %s' % (y, r(A, 0)))

    def ph_t1_port(self, el):
        A = self.D['A']
        if 'fire_t' not in self.D:
            self.aim_at(A)
            if el >= 1.8:
                ok, imp, act, _ = self.cam_ray(ignore=[self.ship])
                self.D['ray'] = {'hit': ok, 'at': r(imp, 0) if imp else None, 'actor': act.get_name() if act else None,
                                 'off_cm': r(dist(imp, A), 1) if imp else None}
                self.fire_side('port')
            return
        self.fire_fallback()
        dt = self.now - self.D['fire_t']
        if dt >= 0.3 and 'mz03' not in self.D:
            self.D['mz03'] = [c for c in self.muzzle_comps(self.ship) if c not in self.D['mz_old']]
            self.capture('t1_muzzle_0.3s', 'port', self.ship)
        if dt >= 1.2 and 'cap12' not in self.D:
            self.D['cap12'] = True
            self.capture('t1_muzzle_1.2s', 'port', self.ship)
        if dt >= 1.5 and 'mz15' not in self.D:
            self.D['mz15'] = self.muzzle_comps(self.ship)

    def end_t1_port(self):
        mz03, mz15 = self.D.get('mz03') or [], self.D.get('mz15')
        self.check('T1.1_muzzle_lifetime', 'PASS' if len(mz03) >= 2 and mz15 == [] else 'FAIL',
                   'port broadside: NS_AirshipMuzzle components under the Mesh %d at +0.3 s (want >= 2), %s at +1.5 s (want 0)%s' % (
                       len(mz03), None if mz15 is None else len(mz15), ' FALLBACK RequestFire' if self.D.get('fb') else ''),
                   {'at_0.3': mz03, 'at_1.5': mz15})
        caps = [s['file'] for s in self.R['shots'] if s['label'].startswith('t1_muzzle')]
        self.check('T1.3_muzzle_captures', 'INFO' if len(caps) == 2 else 'WARN', 'captures for the eye (puffs at 0.3 s, none at 1.2 s): %s' % caps)
        bs = [b for _, b in self.balls_since(self.D.get('fire_t', 1e9), 't1_port')]
        props, okp = [], len(bs) == 2
        for b in bs:
            rel = [b['v0'][i] - (b.get('ship_v') or [0, 0, 0])[i] for i in range(3)]
            spd = math.sqrt(sum(x * x for x in rel))
            props.append({'radius': b.get('radius'), 'mesh_scale': b.get('mesh_scale'), 'gravity': b.get('gravity'), 'launch_cms': r(spd, 1)})
            okp = okp and b.get('radius') is not None and abs(b['radius'] - 50.0) < 0.5 and b.get('mesh_scale') and \
                all(abs(x - 1.0) < 0.01 for x in b['mesh_scale']) and b.get('gravity') is not None and abs(b['gravity'] - 0.6) < 0.01 and \
                abs(spd - 7000.0) <= 70.0
        self.check('T2.1_ball_props', 'PASS' if okp else 'FAIL', '%d port balls (want 2): %s (want radius 50, mesh scale 1.0, gravity 0.6, '
                   '7000 +-1 %% relative to the muzzle)' % (len(bs), props), props)
        A = self.D['A']
        res, ok = [], len(bs) == 2
        for b in bs:
            imp = self.impact_of(b)
            d = dist(imp, A) if imp else None
            apex = self.apex_above_line(b)
            res.append({'impact': imp, 'off_cm': r(d, 1) if d is not None else None, 'apex_cm': apex, 'flight_s': r((b.get('t_hit') or b.get('gone') or 0) - b['t0'], 2)})
            ok = ok and d is not None and d <= 300.0 and apex is not None and apex >= 200.0
        self.check('T2.2_ballistic_150m', 'PASS' if ok else 'FAIL', 'aim %s (camera ray %s): balls %s (want impact within 3 m, apex >= 2 m '
                   'above the muzzle-impact line)' % (r(A, 0), self.D.get('ray'), res), res)

    # ---- T1.2: the asset fix alone (C++ cap off)
    def start_t1_cap0(self):
        self.cmd('Aura.Airship.Set Settings.MuzzleFXMaxSeconds 0')
        r1, r2 = self.geo['R1'], self.geo['R2']
        sl = v3(self.ship.get_actor_location())
        self.D['B'] = [sl[0] + 0.5 * (r1[0] + r2[0]), STBD_FACE_Y, sl[2] + 0.5 * (r1[2] + r2[2])]

    def ph_t1_cap0(self, el):
        if 'fire_t' not in self.D:
            self.aim_at(self.D['B'])
            if el >= 1.2:
                self.fire_side('stbd')
            return
        self.fire_fallback()
        if self.now - self.D['fire_t'] >= 1.2 and 'mz12' not in self.D:
            self.D['mz12'] = self.muzzle_comps(self.ship)

    def end_t1_cap0(self):
        orig = (self.orig.get('settings') or {}).get('MuzzleFXMaxSeconds', 1.0)
        self.cmd('Aura.Airship.Set Settings.MuzzleFXMaxSeconds %s' % orig)
        mz = self.D.get('mz12')
        self.check('T1.2_muzzle_asset_alone', 'PASS' if mz == [] else 'FAIL', 'MuzzleFXMaxSeconds 0 (no C++ cap), stbd broadside: %s NS_AirshipMuzzle '
                   'components at +1.2 s (want 0)' % (None if mz is None else len(mz)), mz)

    # ---- T2.9: a ball on the camera ray doesn't pull the aim
    def start_t2_ray(self):
        self.D['before'], self.D['after'] = [], []

    def aim_vals(self):
        return self.anim(self.ship, ['CannonYawDeg_L1', 'CannonElevDeg_L1', 'CannonYawDeg_L2', 'CannonElevDeg_L2'])

    def ph_t2_ray(self, el):
        A = self.D_A()
        self.aim_at(A)
        if 0.8 <= el < 1.3:
            self.D['before'].append(self.aim_vals())
        if el >= 1.3 and 'ball' not in self.D:
            loc, rot = self.cam()
            p = v3(loc + unreal.MathLibrary.get_forward_vector(rot) * 4000.0)
            self.D['ball'] = self.spawn_ball(p, (0.0, 0.0, 0.0), None, 0.0, 0.0)
            self.D['ball_at'] = r(p, 0)
        if 1.5 <= el < 1.6 and 'ray' not in self.D:
            ok, imp, act, _ = self.cam_ray(ignore=[self.ship])
            self.D['ray'] = {'hit': ok, 'actor': act.get_name() if act else None, 'at': r(imp, 0) if imp else None}
        if 1.8 <= el < 2.3:
            self.D['after'].append(self.aim_vals())
        if el >= 2.5 and self.D.get('ball') is not None and not self.D.get('gone'):
            self.D['gone'] = True
            try:
                if valid(self.D['ball']):
                    self.D['ball'].destroy_actor()
            except Exception:  # noqa: BLE001
                self.err('destroy_ball')

    def D_A(self):
        if 'A' not in self.D:
            _, self.D['A'] = self.port_target(15000.0, PORT_FACE_Y)
            sl = v3(self.ship.get_actor_location())
            self.D['A'][0] += sl[0] - SPAWN[0]
        return self.D['A']

    def end_t2_ray(self):
        ch = {}
        for k in ('CannonYawDeg_L1', 'CannonElevDeg_L1', 'CannonYawDeg_L2', 'CannonElevDeg_L2'):
            a = mean([x[k] for x in self.D['before'] if x.get(k) is not None])
            b = mean([x[k] for x in self.D['after'] if x.get(k) is not None])
            ch[k] = r(b - a, 3) if a is not None and b is not None else None
        on_ray = (self.D.get('ray') or {}).get('actor') and 'annonball' in str((self.D.get('ray') or {}).get('actor'))
        ok = all(v is not None and abs(v) < 0.3 for v in ch.values())
        self.check('T2.9_aim_ignores_balls', ('PASS' if ok else 'FAIL') if on_ray else 'WARN', 'test ball parked on the camera ray at %s (Python '
                   'camera trace hits %s): cannon aim change %s deg (want < 0.3)' % (self.D.get('ball_at'), self.D.get('ray'), ch),
                   {'change': ch, 'ray': self.D.get('ray')})

    # ---- T2.4: 300 m is out of range at the cap
    def start_t2_far(self):
        r1, r2 = self.geo['R1'], self.geo['R2']
        y = PORT_BACK_Y - 30000.0 - 0.5 * (r1[1] + r2[1])
        self.teleport(self.ship, (SPAWN[0], y, SPAWN[2]), 0.0)
        self.D['A'] = [0.5 * (r1[0] + r2[0]), PORT_BACK_Y, SPAWN[2] + 0.5 * (r1[2] + r2[2])]
        self.D['elev'] = []
        self.line('INFO', 'ship 1 at y %.0f: stbd muzzles 300 m from the port wall\'s back face; aim %s' % (y, r(self.D['A'], 0)))

    def ph_t2_far(self, el):
        if 'fire_t' not in self.D:
            self.aim_at(self.D['A'])
            if el >= 1.4:
                self.D['elev'].append(self.anim(self.ship, ['CannonElevDeg_R1', 'CannonElevDeg_R2']))
            if el >= 2.0:
                self.fire_side('stbd')
            return
        self.fire_fallback()

    def end_t2_far(self):
        A = self.D['A']
        e1 = mean([x['CannonElevDeg_R1'] for x in self.D['elev'] if x.get('CannonElevDeg_R1') is not None])
        e2 = mean([x['CannonElevDeg_R2'] for x in self.D['elev'] if x.get('CannonElevDeg_R2') is not None])
        bs = [b for _, b in self.balls_since(self.D.get('fire_t', 1e9), 't2_far')]
        res, short = [], bool(bs)
        for b in bs:
            imp = self.impact_of(b)
            s = imp is None or imp[2] < A[2] - 500.0 or imp[1] < A[1] - 500.0
            res.append({'impact': imp, 'below_aim_cm': r(A[2] - imp[2], 0) if imp else None, 'short': s})
            short = short and s
        cap = e1 is not None and e2 is not None and e1 >= 8.2 and e2 >= 8.2
        self.check('T2.4_out_of_range', 'PASS' if cap and short else 'FAIL', 'aim 300 m level %s: elevation targets R1 %s R2 %s deg (want the 8.5 cap; '
                   'the HUD arc test is not readable from Python, the cap stands for it); balls %s (want short / below the aim)' % (
                       r(A, 0), r(e1, 2) if e1 is not None else None, r(e2, 2) if e2 is not None else None, res), res)

    # ---- T2.3: moving 30 m/s, the aim leads the inherited velocity
    def start_t2_lead(self):
        l1, l2 = self.geo['L1'], self.geo['L2']
        mx = 0.5 * (l1[0] + l2[0])
        y = PORT_FACE_Y + 12000.0 - 0.5 * (l1[1] + l2[1])
        A = [1500.0, PORT_FACE_Y, SPAWN[2] + 0.5 * (l1[2] + l2[2])]
        x_fire = A[0] - 1500.0 - mx                  # mid port muzzle 15 m behind the aim point at the shot
        self.D['FT'] = 1.0
        self.D['x0'] = x_fire - 3000.0 * self.D['FT']
        self.D['A'] = A
        self.D['y'] = y
        self.teleport(self.ship, (self.D['x0'], y, SPAWN[2]), 0.0, (3000.0, 0.0, 0.0))

    def ph_t2_lead(self, el):
        if 'fire_t' not in self.D:
            self.hull(self.ship).set_physics_linear_velocity(unreal.Vector(3000.0, 0.0, 0.0), False, 'None')
            self.aim_at(self.D['A'])
            if el >= self.D['FT']:
                self.D['v_fire'] = r(v3(self.ship.get_velocity()), 1)
                self.D['x_fire'] = r(self.ship.get_actor_location().x, 0)
                self.fire_side('port')
            return
        self.fire_fallback()

    def end_t2_lead(self):
        A = self.D['A']
        bs = [b for _, b in self.balls_since(self.D.get('fire_t', 1e9), 't2_lead')]
        res, ok = [], len(bs) == 2
        for b in bs:
            imp = self.impact_of(b)
            d = dist(imp, A) if imp else None
            res.append({'impact': imp, 'off_cm': r(d, 1) if d is not None else None})
            ok = ok and d is not None and d <= 600.0
        self.check('T2.3_lead_30ms', 'PASS' if ok else 'FAIL', 'ship at %s cm/s (x %s at the shot), aim %s, 120 m off the beam, 15 m ahead (an aim '
                   'abeam would need 24 deg of lead, past the 20 deg yaw limit): balls %s (want within 6 m)' % (
                       self.D.get('v_fire'), self.D.get('x_fire'), r(A, 0), res), res)
        self.teleport(self.ship, SPAWN, 0.0)

    # ---- T4.1 (S): the pilot takes the crew share
    def start_t4_crew(self):
        self.set_scheme(self.ship, self.cfg['scheme'])
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['h0'] = self.health(self.char)

    def ph_t4_crew(self, el):
        if el >= 0.3 and 'dmg' not in self.D:
            self.D['dmg'] = True
            self.D['ship_h0'] = self.tele(self.ship).get('Health')
            self.cmd('Aura.Airship.Damage 100')
        if el >= 1.2 and 'h1' not in self.D:
            self.D['h1'] = self.health(self.char)
            self.D['ph'] = self.tele(self.ship).get('PilotHealth')
            self.D['ship_h1'] = self.tele(self.ship).get('Health')

    def end_t4_crew(self):
        h0, h1 = self.D.get('h0'), self.D.get('h1')
        share = float((self.orig.get('settings') or {}).get('CrewDamageShare', 0.25))
        ok = h0 is not None and h1 is not None and abs((h0 - h1) - 100.0 * share) <= 0.5
        self.check('T4.1_pilot_crew_share_S', 'PASS' if ok else 'FAIL', 'Aura.Airship.Damage 100: ship %s -> %s, pilot %s -> %s (want -%.1f = %.2f x 100), '
                   'telemetry PilotHealth %s' % (self.D.get('ship_h0'), self.D.get('ship_h1'), h0, h1, 100.0 * share, share, self.D.get('ph')))
        self.hp_pilot = h1

    # ---- T4.4 (S) + T9.3: exit at rest keeps the pilot's health; the ship holds
    def start_t9_rest(self):
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['h_before'] = self.health(self.char)
        self.D['locs'], self.D['modes'] = [], []

    def ph_t9_rest(self, el):
        if el >= 0.5 and 'exit' not in self.D:
            self.D['exit'] = True
            self.cmd('Aura.Airship.Exit 0')
        if el >= 1.5 and 'h_after' not in self.D:
            self.D['h_after'] = self.health(self.char)
            self.D['on_foot'] = same(self.pawn(), self.char)
        if el >= 2.0:
            self.D['locs'].append(v3(self.ship.get_actor_location()))
            self.D['modes'].append(self.mode(self.ship))

    def end_t9_rest(self):
        hb, ha = self.D.get('h_before'), self.D.get('h_after')
        self.check('T4.4_exit_keeps_health_S', 'PASS' if hb is not None and ha is not None and abs(hb - ha) <= 0.5 and self.D.get('on_foot') else 'FAIL',
                   'pilot health %s before F exit, %s after (want the same: not refilled), on foot %s' % (hb, ha, self.D.get('on_foot')))
        locs = self.D['locs']
        drift = max(math.hypot(p[0] - locs[0][0], p[1] - locs[0][1]) for p in locs) if locs else None
        modes = sorted(set(self.D['modes']))
        ok = locs and drift < 50.0 and modes == [3]
        self.check('T9.3_hold_at_rest', 'PASS' if ok else 'FAIL', 'exit at rest: modes %s over 30 s (want [3] Hold), moved %s cm horizontally '
                   '(want < 50)' % (modes, r(drift, 1) if drift is not None else None))

    # ---- T5.9 / T5.14 / T5.4 / T5.10 / T5.8 (S): cannon station R1 without a pilot
    def start_t5_cannon(self):
        self.cmd('Aura.Airship.Mount 0 2')

    def ph_t5_cannon(self, el):
        if el >= 0.6 and 'm' not in self.D:
            self.D['m'] = {'gunner': self.gunner(self.ship, 2), 'info': self.char_info(self.char, self.ship),
                           'mask': self.tele(self.ship).get('StationMask'), 'mode': self.mode(self.ship)}
        if el >= 1.0 and 'f1' not in self.D:
            r1 = self.geo['R1']
            sl = v3(self.ship.get_actor_location())
            self.D['B'] = [sl[0] + r1[0], STBD_FACE_Y, sl[2] + r1[2]]
            self.D['f1'] = self.now
            self.D['rec0'] = (self.anim(self.ship, ['CannonRecoilCm_R1']).get('CannonRecoilCm_R1') or 0.0)
            self.cmd('Aura.Airship.StationFire 0 %.0f %.0f %.0f' % tuple(self.D['B']))
        if el >= 1.5 and 'f2' not in self.D:
            self.D['f2'] = self.now
            self.cmd('Aura.Airship.StationFire 0 %.0f %.0f %.0f' % tuple(self.D['B']))
        if 1.0 <= el < 2.4:
            v = self.anim(self.ship, ['CannonRecoilCm_R1']).get('CannonRecoilCm_R1') or 0.0
            self.D['rec_max'] = max(self.D.get('rec_max', 0.0), v)
        if el >= 2.4 and 'balls' not in self.D:
            self.D['balls'] = [(k, b['first']) for k, b in self.balls_since(self.D['f1'], 't5_cannon')]
            self.D['mode2'] = self.mode(self.ship)
        if el >= 3.0 and 'board' not in self.D:
            self.D['board'] = True
            self.cmd('Aura.Airship.Board 0')
        if el >= 3.6 and 'board_res' not in self.D:
            self.D['board_res'] = {'pawn_is_char': same(self.pawn(), self.char), 'ship_pilot': self.ship.get_pilot().get_name() if self.ship.get_pilot() else None}
        if el >= 4.0 and 'dm' not in self.D:
            self.D['dm'] = True
            self.cmd('Aura.Airship.Dismount 0')

    def end_t5_cannon(self):
        m = self.D.get('m') or {}
        i = m.get('info') or {}
        ok = same(m.get('gunner'), self.char) and i.get('att') == self.ship.get_name() and i.get('cmc_tick') is False and \
            i.get('actor_coll') is True and i.get('coll') == 'QUERY_ONLY' and isinstance(m.get('mask'), float) and int(m['mask']) & 4
        self.check('T5.9a_mount_R1_no_pilot', 'PASS' if ok else 'FAIL', 'Aura.Airship.Mount 0 2 with no pilot: station 2 gunner %s, character %s, '
                   'StationMask %s, ship mode %s' % (m.get('gunner').get_name() if m.get('gunner') else None, i, m.get('mask'), m.get('mode')))
        self.check('T5.14_gunner_collision_S', 'PASS' if i.get('actor_coll') is True and i.get('coll') == 'QUERY_ONLY' else 'FAIL',
                   'mounted gunner: actor collision %s, capsule %s (want on, QUERY_ONLY)' % (i.get('actor_coll'), i.get('coll')))
        bl = self.D.get('balls') or []
        r1w = self.world_of(self.ship, self.geo['R1'])
        near = [b for b in bl if dist(b[1], r1w) < 600.0]
        ok2 = len(bl) == 1 and len(near) == 1 and self.D.get('mode2') == m.get('mode') and (self.D.get('rec_max') or 0) > 5.0
        self.check('T5.9_station_fire_S', 'PASS' if ok2 else 'FAIL', 'StationFire at %s, again 0.5 s later: %d ball(s) %s (want 1, from R1 near %s), '
                   'recoil R1 max %s cm, ship mode %s -> %s (unchanged)' % (r(self.D.get('B'), 0), len(bl), bl, r(r1w, 0), self.D.get('rec_max'),
                                                                           m.get('mode'), self.D.get('mode2')))
        br = self.D.get('board_res') or {}
        self.check('T5.10_board_refused_S', 'PASS' if br.get('pawn_is_char') and not br.get('ship_pilot') else 'FAIL',
                   'Aura.Airship.Board 0 while mounted: %s (want refused: still the character, no pilot)' % br)
        fi = self.char_info(self.char, self.ship) or {}
        ok3 = fi.get('att') is None and fi.get('cmc_tick') is True and fi.get('mode') in ('MOVE_WALKING', 'MOVE_FALLING') and self.gunner(self.ship, 2) is None
        self.check('T5.8_dismount_S', 'PASS' if ok3 else 'FAIL', 'Aura.Airship.Dismount 0: %s, station 2 %s (want detached, CMC ticking, '
                   'walking / falling, free)' % (fi, self.gunner(self.ship, 2)))

    # ---- T6.4 / T6.8: the turrets hit ship 2 60 m ahead
    def start_t6_hit(self):
        self.teleport(self.ship, S1_T6, 0.0)
        self.teleport(self.ship2, PARK2, 0.0)
        self.D['s0'] = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]
        self.D['s2'] = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship2)]

    def ph_t6_hit(self, el):
        if el >= 0.8 and 'on' not in self.D:
            self.D['on'] = True
            self.D['h2_0'] = self.tele(self.ship2).get('Health')
            p = v3(self.ship2.get_actor_location())
            self.D['P'] = [p[0], p[1], p[2] + 300.0]
            self.local['turret_fire_on'] = True
            self.cmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(self.D['P']))
        if el >= 1.8 and 'off' not in self.D:
            self.D['off'] = True
            self.cmd('Aura.Airship.TurretFire 0')
            self.local['turret_fire_on'] = False

    def end_t6_hit(self):
        h0, h1 = self.D.get('h2_0'), self.tele(self.ship2).get('Health')
        s1 = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]
        shots = sum(s1[i] - self.D['s0'][i] for i in range(min(len(s1), len(self.D['s0']))))
        s2 = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship2)]
        drop = (h0 - h1) if h0 is not None and h1 is not None else None
        mult = float((self.orig.get('settings') or {}).get('TurretGunDamageMultiplier', 4.0))
        exp = 20.0 * mult * self.gun_base
        ok = drop is not None and abs(drop - exp) <= 0.25 * exp
        self.check('T6.4_turrets_hit_ship2', 'PASS' if ok else 'FAIL', 'TurretFire 1 s at %s: ship 2 %s -> %s (drop %s, want %.0f +-25 %% = 20 x %.0f x '
                   'gun %.2f); ship 1 shots %d, ship 2 shots %s -> %s (its turrets face away: want unchanged)' % (
                       r(self.D.get('P'), 0), h0, h1, drop, exp, mult, self.gun_base, shots, self.D['s2'], s2))
        per = drop / shots if drop is not None and shots else None
        want = mult * self.gun_base
        self.check('T6.8_bullet_damage', 'PASS' if per is not None and abs(per - want) <= 0.1 * want else 'FAIL',
                   'damage per bullet %s (drop %s / %d shots) vs %.0f x GE_GunShootDamage %.3f = %.3f' % (r(per, 3) if per else None, drop, shots, mult,
                                                                                                         self.gun_base, want))

    # ---- T6.9: turret rounds at an enemy turret, through that ship's hull collision (Visibility on)
    def start_t6_turret(self):
        # t6_hit left ship 1 parked with its turret muzzles about 60 m behind ship 2's stern
        ts = self.turrets(self.ship2)
        self.D['t'] = next((t for t in ts if call(t, 'get_turret_index') == 0), ts[0] if ts else None)
        self.D['s0'] = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]

    def ph_t6_turret(self, el):
        t = self.D.get('t')
        if t is None:
            return
        if el >= 0.5 and 'on' not in self.D:
            self.D['on'] = True
            P = v3(t.get_editor_property('HitBox').get_world_location())
            self.D['P'] = P
            self.D['h0'] = (self.tstate(t).get('health'), self.tele(self.ship2).get('Health'))
            own = self.turrets(self.ship)
            o0 = next((x for x in own if call(x, 'get_turret_index') == 0), own[0] if own else None)
            if o0 is not None:
                m = v3(o0.get_editor_property('Muzzle').get_world_location())
                self.D['line'] = self.trace(m, P, [self.ship] + own)
            self.local['turret_fire_on'] = True
            self.cmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(P))
        if el >= 1.5 and 'off' not in self.D:
            self.D['off'] = True
            self.cmd('Aura.Airship.TurretFire 0')
            self.local['turret_fire_on'] = False
        if el >= 2.5 and 'h1' not in self.D and 'h0' in self.D:
            self.D['h1'] = (self.tstate(t).get('health'), self.tele(self.ship2).get('Health'))

    def end_t6_turret(self):
        if self.D.get('t') is None:
            self.check('T6.9_turret_through_hull', 'FAIL', 'ship 2 has no turret')
            return
        h0, h1 = self.D.get('h0') or (None, None), self.D.get('h1') or (None, None)
        s1 = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]
        shots = sum(s1[i] - self.D['s0'][i] for i in range(min(len(s1), len(self.D['s0']))))
        step = float((self.orig.get('settings') or {}).get('TurretGunDamageMultiplier', 4.0)) * self.gun_base
        drop = (h0[0] - h1[0]) if h0[0] is not None and h1[0] is not None else None
        hits = drop / step if drop is not None and step > 0.0 else None
        ok = hits is not None and drop > 0.0 and abs(hits - round(hits)) < 0.01
        first = (self.D.get('line') or {}).get('actor')
        self.check('T6.9_turret_through_hull', 'PASS' if ok else 'FAIL', 'TurretFire 1 s from ship 1 at ship 2\'s port turret HitBox %s, ship 2\'s '
                   'hull Visibility on: first Visibility hit from ship 1\'s muzzle %s (want ship 2\'s hull: the turret sits inside its forward '
                   'deck convex); turret %s -> %s (drop %s = %s bullets of %.2f, want > 0 whole bullets); ship 2 %s -> %s (the spread\'s misses '
                   'hit the hull); %d shots' % (r(self.D.get('P'), 0), self.D.get('line'), h0[0], h1[0], drop, r(hits, 2) if hits is not None else None,
                                                step, h0[1], h1[1], shots), {'first_hit': first})

    # ---- T6.5: never the own ship's riders
    def start_t6_own(self):
        self.D['s0'] = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]
        loc, traced = self.deck_point(self.ship, 2700.0, 0.0)
        self.tp_char(loc, self.ship.get_actor_rotation().yaw)
        self.line('INFO', 'player on ship 1\'s forward deck at %s (hull trace %s)' % (r(loc, 0), traced))

    def ph_t6_own(self, el):
        if el >= 0.8 and 'on' not in self.D:
            self.D['on'] = True
            self.D['h0'] = (self.health(self.char), self.tele(self.ship).get('Health'))
            self.D['rider'] = (self.char_info(self.char, self.ship) or {}).get('rider')
            p = v3(self.char.get_actor_location())
            self.local['turret_fire_on'] = True
            self.cmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(p))
        if el >= 1.8 and 'off' not in self.D:
            self.D['off'] = True
            self.cmd('Aura.Airship.TurretFire 0')
            self.local['turret_fire_on'] = False

    def end_t6_own(self):
        h1 = (self.health(self.char), self.tele(self.ship).get('Health'))
        s1 = [self.tstate(t).get('shots') or 0 for t in self.turrets(self.ship)]
        shots = sum(s1[i] - self.D['s0'][i] for i in range(min(len(s1), len(self.D['s0']))))
        h0 = self.D.get('h0') or (None, None)
        ok = h0[0] is not None and abs(h0[0] - h1[0]) < 0.01 and h0[1] is not None and abs(h0[1] - h1[1]) < 0.01
        self.check('T6.5_no_own_rider_damage', ('PASS' if ok else 'FAIL') if shots else 'WARN', 'TurretFire at the rider on ship 1\'s deck (rider %s): '
                   'rider %s -> %s, ship 1 %s -> %s, %d shots fired%s' % (self.D.get('rider'), h0[0], h1[0], h0[1], h1[1], shots,
                                                                       '' if shots else ' (no shots: the test proves nothing)'))

    # ---- T5.6 / T5.7 (S): manned turret L, trigger 1 s then 3.5 s
    def start_t5_turret(self):
        self.cmd('Aura.Airship.Mount 0 4')
        self.D['trk'] = []

    def ph_t5_turret(self, el):
        ts = self.turrets(self.ship)
        t0 = next((t for t in ts if (call(t, 'get_turret_index') if hasattr(t, 'get_turret_index') else -1) == 0), ts[0] if ts else None)
        if t0 is None:
            return
        st = self.tstate(t0)
        self.D['trk'].append((r(el, 3), st.get('shots'), st.get('heat'), st.get('overheated')))
        if el >= 0.6 and 'm' not in self.D:
            self.D['m'] = {'gunner': self.gunner(self.ship, 4), 'att': (self.char_info(self.char, self.ship) or {}).get('att')}
        if el >= 1.0 and 'f1' not in self.D:
            sl, fw = v3(self.ship.get_actor_location()), v3(self.ship.get_actor_forward_vector())
            self.D['Q'] = [sl[0] + fw[0] * 9000.0, sl[1] + fw[1] * 9000.0, sl[2] + 800.0]
            self.D['f1'] = st.get('shots') or 0
            self.cmd('Aura.Airship.StationFire 0 %.0f %.0f %.0f 1.0' % tuple(self.D['Q']))
        if el >= 2.3 and 'r1' not in self.D:
            self.D['r1'] = ((st.get('shots') or 0) - self.D['f1'], st.get('heat'))
        if el >= 3.5 and 'f2' not in self.D:
            self.D['f2'] = True
            self.cmd('Aura.Airship.StationFire 0 %.0f %.0f %.0f 3.5' % tuple(self.D['Q']))

    def end_t5_turret(self):
        m = self.D.get('m') or {}
        ok_m = same(m.get('gunner'), self.char) and m.get('att') == self.ship.get_name()
        n1, h1 = self.D.get('r1') or (None, None)
        self.check('T5.6_turret_station_S', 'PASS' if ok_m and n1 is not None and 9 <= n1 <= 11 and h1 is not None and 0.25 <= h1 <= 0.42 else 'FAIL',
                   'Mount 0 4 (gunner %s, attached to %s); StationFire 1.0 s at %s: %s shots (want 9-11), heat %s (want ~0.33)' % (
                       m.get('gunner').get_name() if m.get('gunner') else None, m.get('att'), r(self.D.get('Q'), 0), n1, h1))
        trk = [x for x in self.D['trk'] if x[0] >= 3.5]
        t_oh = next((x[0] for x in trk if x[3]), None)
        shots_oh = None
        t_rec = None
        if t_oh is not None:
            after = [x for x in trk if x[0] > t_oh]
            t_rec = next((x[0] for x in after if not x[3]), None)
            window = [x for x in trk if t_oh <= x[0] <= (t_rec if t_rec is not None else 1e9)]
            shots_oh = (window[-1][1] - window[0][1]) if window and window[0][1] is not None and window[-1][1] is not None else None
            heat_rec = next((x[2] for x in after if not x[3]), None)
        else:
            heat_rec = None
        ok = t_oh is not None and 2.6 <= t_oh - 3.5 <= 3.4 and shots_oh == 0 and t_rec is not None and heat_rec is not None and heat_rec <= 0.36
        self.check('T5.7_overheat_S', 'PASS' if ok else 'FAIL', 'trigger held 3.5 s from 3.5 s: overheat at %s s into the hold (want ~3), %s shots while '
                   'overheated (want 0), recovered at %s (%s s after release, heat %s, want <= 0.35)' % (
                       r(t_oh - 3.5, 2) if t_oh is not None else None, shots_oh, t_rec,
                       r(t_rec - 7.0, 2) if t_rec is not None else None, heat_rec))

    # ---- T6.6 (S): the manned turret is destroyed
    def start_t6_destroy(self):
        self.D['t0'] = next((t for t in self.turrets(self.ship) if (call(t, 'get_turret_index') if hasattr(t, 'get_turret_index') else -1) == 0), None)
        self.cmd('Aura.Airship.TurretDamage 0 400')

    def ph_t6_destroy(self, el):
        t0 = self.D.get('t0')
        if el >= 0.6 and 'st' not in self.D and t0 is not None:
            fx = None
            try:
                fx = bool(t0.get_editor_property('DestroyedFXComponent').is_active())
            except Exception:  # noqa: BLE001
                self.err('destroyed_fx')
            self.D['st'] = {'turret': self.tstate(t0), 'fire_fx': fx, 'gunner': self.gunner(self.ship, 4), 'char': self.char_info(self.char, self.ship)}
        if el >= 1.0 and 'on' not in self.D:
            self.D['on'] = True
            self.D['s0'] = dict((call(t, 'get_turret_index'), self.tstate(t).get('shots') or 0) for t in self.turrets(self.ship))
            sl, fw = v3(self.ship.get_actor_location()), v3(self.ship.get_actor_forward_vector())
            q = [sl[0] + fw[0] * 9000.0, sl[1] + fw[1] * 9000.0, sl[2] + 800.0]
            self.local['turret_fire_on'] = True
            self.cmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(q))
        if el >= 2.0 and 'off' not in self.D:
            self.D['off'] = True
            self.cmd('Aura.Airship.TurretFire 0')
            self.local['turret_fire_on'] = False

    def end_t6_destroy(self):
        st = self.D.get('st') or {}
        s1 = dict((call(t, 'get_turret_index'), self.tstate(t).get('shots') or 0) for t in self.turrets(self.ship))
        s0 = self.D.get('s0') or {}
        d = dict((k, s1.get(k, 0) - s0.get(k, 0)) for k in s1)
        ci = st.get('char') or {}
        ok = (st.get('turret') or {}).get('destroyed') and st.get('fire_fx') and st.get('gunner') is None and ci.get('att') is None and \
            d.get(0, 0) == 0 and d.get(1, 0) > 0
        self.check('T6.6_turret_destroyed_S', 'PASS' if ok else 'FAIL', 'TurretDamage 0 400 with the player on it: turret 0 %s, fire FX active %s, '
                   'station 4 %s, player %s; TurretFire 1 s after: shots per turret %s (want 0 from turret 0, > 0 from turret 1)' % (
                       st.get('turret'), st.get('fire_fx'), st.get('gunner'), ci, d))

    # ---- T3.1 / T3.2 / T3.3: sentinel test bullets
    def start_t3_bullets(self):
        self.teleport(self.ship, SPAWN, 0.0)
        self.tp_char(CHAR_FOOT, 0.0)
        m = self.ship.get_editor_property('Mesh')
        self.D['mesh_coll'] = m.get_collision_enabled()
        m.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)

    def bullet(self, frm, to, key):
        self.D[key + '_trace'] = self.trace(frm, to)
        self.cmd('Aura.MechSentinel.TestBullet %.0f %.0f %.0f %.0f %.0f %.0f 3' % (tuple(frm) + tuple(to)))

    def ph_t3_bullets(self, el):
        if el >= 0.5 and 'b1' not in self.D:
            self.D['b1'] = True
            self.D['h1'] = self.tele(self.ship).get('Health')
            to = v3(self.ship.get_actor_location())
            to[2] += 300.0
            frm = [to[0], to[1] - 1200.0 - 2500.0, to[2]]
            self.bullet(frm, to, 'b1')
        if el >= 2.0 and 'r1' not in self.D:
            self.D['r1'] = self.tele(self.ship).get('Health')
        if el >= 2.2 and 'b2' not in self.D:
            self.D['b2'] = True
            ts = [t for t in self.turrets(self.ship) if not self.tstate(t).get('destroyed')]
            if not ts:
                self.D['b2_none'] = True
                return
            t = ts[0]
            self.D['t'] = t
            hb = t.get_editor_property('HitBox')
            to = v3(hb.get_world_location())
            side = -1.0 if (call(t, 'get_turret_index') == 0) else 1.0
            rg = v3(self.ship.get_actor_right_vector())
            frm = [to[i] + rg[i] * side * 2500.0 for i in range(3)]
            self.D['h2'] = (self.tstate(t).get('health'), self.tele(self.ship).get('Health'))
            # The hull keeps its Visibility block: the turret sits inside the forward deck's convex (UCX_01), the line meets
            # the hull first and the swarm's redirect (AAirshipPawn::RedirectBulletHitToTurret) hands the hit to the turret
            self.bullet(frm, to, 'b2')
        if el >= 3.8 and 'r2' not in self.D and self.D.get('t') is not None:
            self.D['r2'] = (self.tstate(self.D['t']).get('health'), self.tele(self.ship).get('Health'))
        if el >= 3.9 and 'mesh_back' not in self.D:
            self.D['mesh_back'] = True
            self.ship.get_editor_property('Mesh').set_collision_enabled(self.D['mesh_coll'])
        if el >= 4.2 and 'b3' not in self.D:
            self.D['b3'] = True
            self.D['h3'] = self.health(self.char)
            to = v3(self.char.get_actor_location())
            frm = [to[0], to[1] - 2500.0, to[2]]
            self.bullet(frm, to, 'b3')
        if el >= 6.0 and 'r3' not in self.D:
            self.D['r3'] = self.health(self.char)

    def end_t3_bullets(self):
        if not self.D.get('mesh_back') and 'mesh_coll' in self.D:
            self.ship.get_editor_property('Mesh').set_collision_enabled(self.D['mesh_coll'])
        h1, r1 = self.D.get('h1'), self.D.get('r1')
        self.check('T3.1_bullet_hull', 'PASS' if h1 is not None and r1 is not None and abs((h1 - r1) - 3.0) < 0.05 else 'FAIL',
                   'TestBullet 25 m to port at the hull (Mesh collision off: no PA bodies): ship %s -> %s (want -3); first Visibility hit on the '
                   'line %s' % (h1, r1, self.D.get('b1_trace')))
        if self.D.get('b2_none'):
            self.check('T3.2_bullet_turret', 'FAIL', 'no living turret on ship 1')
        else:
            a, b = self.D.get('h2') or (None, None), self.D.get('r2') or (None, None)
            ok = a[0] is not None and b[0] is not None and abs((a[0] - b[0]) - 3.0) < 0.05 and a[1] is not None and b[1] is not None and abs(a[1] - b[1]) < 0.01
            first = (self.D.get('b2_trace') or {}).get('actor')
            self.check('T3.2_bullet_turret', 'PASS' if ok else 'FAIL', 'TestBullet from 25 m outboard at the HitBox, the hull\'s Visibility on: turret '
                       '%s -> %s (want -3), ship %s -> %s (want unchanged); first Visibility hit on the line %s (%s: the redirect %s)' % (
                           a[0], b[0], a[1], b[1], self.D.get('b2_trace'), first,
                           'was needed' if first == self.ship.get_name() else 'was not needed (the line reached the turret directly)'))
        h3, r3 = self.D.get('h3'), self.D.get('r3')
        self.check('T3.3_bullet_character', 'PASS' if h3 is not None and r3 is not None and abs((h3 - r3) - 3.0) < 0.05 else 'FAIL',
                   'TestBullet at the on-foot player: %s -> %s (want -3 through the Pawn sweep, as before)' % (h3, r3))

    # ---- T2.6: the player shoots a ball down (GA_GunShoot), no splash
    def start_t2_gun(self):
        self.teleport(self.ship, SPAWN, 0.0)
        o, e = self.ship.get_actor_bounds(False)
        ymin = o.y - e.y
        self.D['B0'] = [-900.0, ymin - 100.0 - 50.0, SPAWN[2] + 300.0]
        self.tp_char([-1500.0, self.D['B0'][1] - 1500.0, 150.0], 90.0)
        self.D['ball'] = self.spawn_ball(self.D['B0'], (200.0, 0.0, 0.0), self.ship2, 60.0, 0.0)
        self.D['hp'] = []
        self.D['n'] = 0

    def ph_t2_gun(self, el):
        b = self.D.get('ball')
        if not valid(b):
            return
        st = self.ball_state(b)
        if not self.D['hp'] or self.D['hp'][-1][1] != st.get('health') or self.D['hp'][-1][2] != st.get('shot_down'):
            self.D['hp'].append((r(el, 3), st.get('health'), st.get('shot_down')))
        if st.get('shot_down'):
            if 'down_t' not in self.D:
                self.D['down_t'] = el
                self.D['h_at_down'] = (self.tele(self.ship).get('Health'), self.health(self.char), self.tele(self.ship2).get('Health'))
            if el >= self.D['down_t'] + 1.0 and 'h_after' not in self.D:
                self.D['h_after'] = (self.tele(self.ship).get('Health'), self.health(self.char), self.tele(self.ship2).get('Health'))
            return
        self.aim_at(v3(b.get_actor_location()))
        if 0.6 <= el < 10.5:
            self.inject('IA_LMB')
            self.D['n'] += 1
        if el >= 2.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('t2_gun_view', 'player')

    def end_t2_gun(self):
        hp = [x for x in self.D['hp'] if x[1] is not None]
        drops = [round(hp[i][1] - hp[i + 1][1], 3) for i in range(len(hp) - 1) if hp[i + 1][1] < hp[i][1]]
        down = self.D.get('down_t') is not None
        a, b = self.D.get('h_at_down'), self.D.get('h_after')
        nosplash = a is not None and b is not None and all(x is not None and y is not None and abs(x - y) < 0.01 for x, y in zip(a, b))
        ok = down and len(drops) == 30 and all(abs(d - 1.0) < 1e-3 for d in drops) and nosplash
        self.check('T2.6_gun_shoots_ball', 'PASS' if ok else 'FAIL', 'ball (ship 2\'s, 60 damage) 1 m off ship 1\'s hull, the player fires GA_GunShoot '
                   '(IA_LMB %d frames): %d hits %s, shot down %s at %s s; ship 1 / player / ship 2 health at the shoot-down %s, 1 s later %s (want 30 '
                   'hits of 1, shot down, no change: no splash)' % (self.D['n'], len(drops), sorted(set(drops)), down, self.D.get('down_t'), a, b),
                   {'health_track': hp})

    # ---- T2.5 (character dummy): splash falloff
    def start_t2_splash(self):
        P = [POST_LOC[0], POST_FACE_Y, 100.0]
        self.D['P'] = P
        self.tp_char([P[0] + 550.0, P[1] - 30.0, 150.0], 0.0)
        self.D['h0'] = None

    def ph_t2_splash(self, el):
        if el >= 0.8 and 'ball' not in self.D:
            self.D['h0'] = self.health(self.char)
            P = self.D['P']
            self.D['ball'] = self.spawn_ball([P[0], P[1] - 400.0, P[2]], (0.0, 2000.0, 0.0), self.ship2, 60.0, 0.0)
            self.D['t_ball'] = self.now
        if 'ball' in self.D and 'char_at' not in self.D:
            bs = [b for _, b in self.balls_since(self.D['t_ball'], 't2_splash') if b.get('t_hidden') or b.get('stopped')]
            if bs:
                self.D['char_at'] = v3(self.char.get_actor_location())
                self.D['impact'] = self.impact_of(bs[0])

    def end_t2_splash(self):
        h0, h1 = self.D.get('h0'), self.health(self.char)
        imp, ca = self.D.get('impact'), self.D.get('char_at')
        d = dist(imp, ca) if imp and ca else None
        exp = 60.0 * (1.0 - 0.7 * min(1.0, d / 600.0)) if d is not None else None
        drop = (h0 - h1) if h0 is not None and h1 is not None else None
        ok = exp is not None and drop is not None and d < 600.0 and abs(drop - exp) <= 0.15 * exp
        self.check('T2.5_splash_falloff', 'PASS' if ok else 'FAIL', 'ball into %sSplashPost, the player %s cm from the impact %s: health drop %s, '
                   'want %s +-15 %% (60 x lerp(1, 0.3, d / 600)). A ship dummy can\'t be 5.5 m from an outside impact (51 x 24 m hull, the '
                   'splash measures to the actor\'s centre), so the on-foot player stands in' % (TEMP59, r(d, 0) if d else None, imp, r(drop, 2) if drop else drop,
                                                                                            r(exp, 2) if exp else None))

    # ---- T9.1 / T9.2 / T9.5: drift after a moving exit, per scheme
    def start_t9_drift(self):
        self.cmd('Aura.Airship.Board 0')
        self.D['trk'] = []

    def ph_t9_drift(self, el):
        s = self.D['scheme']
        if el >= 0.2 and 'sch' not in self.D:
            self.D['sch'] = True
            self.set_scheme(self.ship, s)
        if el >= 0.5 and 'tp' not in self.D:
            self.D['tp'] = True
            self.teleport(self.ship, SPAWN, 0.0, (DRIFT_EXIT_CMS, 0.0, 0.0))
            self.D['yaw0'] = self.ship.get_actor_rotation().yaw
        if el >= 0.7 and 'exit' not in self.D:
            self.D['exit'] = True
            self.D['v_exit'] = self.tele(self.ship).get('ForwardSpeedMS')
            self.cmd('Aura.Airship.Exit 0')
        if el >= 1.0 and 'board2' not in self.D:
            t = self.tele(self.ship)
            self.D['trk'].append((r(el, 2), t.get('UnpilotedMode'), t.get('ForwardSpeedMS'), math.hypot(*(v3(self.ship.get_velocity())[:2])) / 100.0,
                                  self.ship.get_actor_rotation().yaw, t.get('Throttle'), t.get('DriftTargetSpeedMS')))
        if el >= 38.0 and 'board2' not in self.D:
            self.D['board2'] = True
            self.cmd('Aura.Airship.Board 0')
        if el >= 38.6 and 'thr' not in self.D:
            self.D['thr'] = True
            self.D['mode_board'] = self.mode(self.ship)
            self.D['vf0'] = self.tele(self.ship).get('ForwardSpeedMS')
            self.ship.debug_set_input(1.0, 0.0, 0.0, 0.0, False, False)
        if el >= 39.8 and 'vf1' not in self.D:
            self.D['vf1'] = self.tele(self.ship).get('ForwardSpeedMS')
            self.ship.debug_clear_input()

    def end_t9_drift(self):
        s = self.D['scheme']
        name = SCHEME_NAMES.get(s)
        trk = self.D['trk']
        modes = sorted(set(int(x[1]) for x in trk if x[0] >= 1.5 and x[1] is not None))
        late = [x[3] for x in trk if x[0] >= 30.0]
        v_late = mean(late)
        dyaw = max(abs(wrap180(x[4] - self.D.get('yaw0', 0.0))) for x in trk) if trk else None
        rev = min((x[5] for x in trk if x[5] is not None), default=None)
        ok = modes == [2] and v_late is not None and abs(v_late - 2.5) <= 0.3 and dyaw is not None and dyaw < 2.0 and (rev is None or rev >= -0.01)
        key = 'T9.1_drift_P&F' if s == 3 else 'T9.2_drift_%s' % name
        self.check(key, 'PASS' if ok else 'FAIL', '%s: exit at %s m/s; modes %s (want [2] Drift), speed %s m/s from 30 s (want 2.5 +-0.3), heading '
                   'change %s deg (want < 2), lowest shaped throttle %s (want >= 0: no reverse, the fans idle)' % (
                       name, self.D.get('v_exit'), modes, r(v_late, 2) if v_late is not None else None, r(dyaw, 2) if dyaw is not None else None, rev),
                   {'track': trk[::10]})
        vf0, vf1 = self.D.get('vf0'), self.D.get('vf1')
        ok2 = self.D.get('mode_board') == 0 and vf0 is not None and vf1 is not None and vf1 > vf0 + 0.3
        self.check('T9.5_board_while_drifting_%s' % name, 'PASS' if ok2 else 'FAIL', 'Board while drifting: mode %s (want 0 None), throttle 1 for '
                   '1.2 s: forward speed %s -> %s m/s (want up)' % (self.D.get('mode_board'), vf0, vf1))

    # ---- T9.4: drifting toward the port wall
    def start_t9_wall(self):
        self.cmd('Aura.Airship.Board 0')
        self.D['trk'] = []

    def ph_t9_wall(self, el):
        if el >= 0.2 and 'tp' not in self.D:
            self.D['tp'] = True
            self.set_scheme(self.ship, self.cfg['scheme'])
            self.teleport(self.ship, WALL_START, -90.0, (0.0, -500.0, 0.0))
        if el >= 0.5 and 'exit' not in self.D:
            self.D['exit'] = True
            self.D['h0'] = self.tele(self.ship).get('Health')
            self.cmd('Aura.Airship.Exit 0')
        if el >= 0.6:
            o, e, _ = unreal.SystemLibrary.get_component_bounds(self.hull(self.ship))
            self.D['trk'].append((r(el, 2), self.mode(self.ship), r(o.y - e.y - PORT_FACE_Y, 1), r(v3(self.ship.get_velocity())[1], 1)))

    def end_t9_wall(self):
        trk = self.D['trk']
        gap = min(x[2] for x in trk) if trk else None
        final = trk[-1][1] if trk else None
        h1 = self.tele(self.ship).get('Health')
        h0 = self.D.get('h0')
        nodmg = h0 is not None and h1 is not None and abs(h0 - h1) < 0.01
        ok = final == 3 and gap is not None and (gap >= 50.0 or gap <= 5.0) and nodmg
        self.check('T9.4_drift_wall', 'PASS' if ok else 'FAIL', 'drift toward the port wall: closest hull-bounds gap %s cm (want >= 50 short, or '
                   'contact), final mode %s (want 3 Hold), health %s -> %s (want unchanged); track %s' % (gap, final, h0, h1, trk[::25]))

    # ---- T9.6: debug input on an unpiloted ship, then cleared at speed
    def start_t9_input(self):
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['trk'] = []

    def ph_t9_input(self, el):
        if el >= 0.5 and 'in' not in self.D:
            self.D['in'] = True
            self.cmd('Aura.Airship.Input 1 0')
        if el >= 6.5 and 'clr' not in self.D:
            self.D['clr'] = True
            self.cmd('Aura.Airship.InputClear')
        t = self.tele(self.ship)
        self.D['trk'].append((r(el, 2), t.get('UnpilotedMode'), t.get('SpeedMS')))

    def end_t9_input(self):
        trk = self.D['trk']
        during = sorted(set(int(x[1]) for x in trk if 1.0 <= x[0] < 6.4 and x[1] is not None))
        after = [x for x in trk if x[0] >= 6.6 and x[1] is not None]
        first = int(after[0][1]) if after else None
        v_clear = after[0][2] if after else None
        hold = next((x for x in after if int(x[1]) == 3), None)
        ok = during == [0] and (first == 1 or (v_clear is not None and v_clear < 3.0 and first == 3)) and hold is not None and (hold[2] or 0) < 3.0 \
            and int(after[-1][1]) == 3
        self.check('T9.6_debug_input_then_coast', 'PASS' if ok else 'FAIL', 'Aura.Airship.Input 1 0: modes %s (want [0] None); cleared at %s m/s: first '
                   'mode %s (want 1 Coast), Hold at %s (want once below 3 m/s), final %s' % (
                       during, v_clear, first, hold[:3] if hold else None, after[-1][1] if after else None))

    # ---- T7.2 / T7.3: helm and deck captures, the wheel's measured size
    def start_t7_caps(self):
        self.teleport(self.ship, SPAWN, 0.0)
        self.cmd('Aura.Airship.Board 0')

    def ph_t7_caps(self, el):
        if el >= 1.5 and 'c' not in self.D:
            self.D['c'] = True
            for k in ('helm', 'top', 'bow'):
                self.capture('t7_%s' % k, k, self.ship)
            self.capture('t7_pilot_view', 'player')

    def end_t7_caps(self):
        size = None
        try:
            with open(PART_BOUNDS) as f:
                pb = json.load(f)['bones']
            hw = pb.get('Helm_Wheel') or {}
            size = max(hw.get('size', [0, 0, 0])[1:])
        except Exception:  # noqa: BLE001
            self.err('part_bounds')
        self.check('T7.2_wheel_size', 'PASS' if size is not None and 136.0 <= size <= 144.0 else 'FAIL', 'Helm_Wheel vertex bounds across %s cm '
                   '(Saved/Airship/part_bounds.json, as_09; want 136-144); captures %s' % (
                       size, [s['file'] for s in self.R['shots'] if s['label'].startswith('t7_')]))
        self.check('T7.3_deck_capture', 'INFO', 'top / bow captures for the eye: the 5 pieces gone, the turrets at the forward deck edges: %s'
                   % [s['file'] for s in self.R['shots'] if s['label'] in ('t7_top', 't7_bow')])

    # ---- T5.11 (S): ship death ejects its gunner alive
    def start_t5_kill(self):
        # D4 gives the crew 25 % of every Health loss, so a kill from full health would kill the gunner too (eject, then the
        # on-foot death): the spec's T5.11 wants the eject on ship death, so the share is off for this phase only
        self.cmd('Aura.Airship.Exit 0')
        self.cmd('Aura.Airship.Set Settings.CrewDamageShare 0')

    def ph_t5_kill(self, el):
        if el >= 0.4 and 'm' not in self.D:
            self.D['m'] = True
            self.cmd('Aura.Airship.Mount 0 3')
        if el >= 1.0 and 'k' not in self.D:
            self.D['k'] = True
            self.D['pre'] = {'gunner': self.gunner(self.ship, 3), 'att': (self.char_info(self.char, self.ship) or {}).get('att')}
            try:
                self.ship.apply_ship_damage(1.0e6)
            except Exception:  # noqa: BLE001
                self.err('kill_ship')
        if el >= 1.6 and 'post' not in self.D:
            self.D['post'] = {'dead': bool(self.ship.is_airship_dead()), 'gunner': self.gunner(self.ship, 3), 'char': self.char_info(self.char, self.ship)}

    def end_t5_kill(self):
        self.cmd('Aura.Airship.Set Settings.CrewDamageShare %s' % (self.orig.get('settings') or {}).get('CrewDamageShare', 0.25))
        pre, post = self.D.get('pre') or {}, self.D.get('post') or {}
        ci = post.get('char') or {}
        ok = same(pre.get('gunner'), self.char) and post.get('dead') and post.get('gunner') is None and ci.get('att') is None and \
            ci.get('cmc_tick') is True and (ci.get('health') or 0) > 0
        self.check('T5.11_ship_death_ejects_gunner_S', 'PASS' if ok else 'FAIL', 'gunner on R2 %s, ship 1 killed (ApplyShipDamage, CrewDamageShare 0 '
                   'for the phase): dead %s, station 3 '
                   '%s, player %s (want detached, CMC ticking, alive)' % (pre, post.get('dead'), post.get('gunner'), ci))

    # ---- T4.2 (S): the crew share would kill the pilot: ejected first, then the on-foot death
    def start_t4_kill(self):
        self.cmd('Aura.Airship.Board 0')     # ship 1 is dead: the nearest free living ship is ship 2

    def ph_t4_kill(self, el):
        if el >= 0.6 and 'low' not in self.D:
            self.D['low'] = True
            self.D['pilot_ok'] = same(self.ship2.get_pilot(), self.char)
            h = self.health(self.char)
            if h is not None and h > 10.0:
                self.hurt(self.char, h - 10.0)
        if el >= 1.0 and 'dmg' not in self.D:
            self.D['dmg'] = True
            self.D['h_low'] = self.health(self.char)
            self.cmd('Aura.Airship.Damage 100')
        if el >= 2.0 and 'post' not in self.D:
            self.D['post'] = {'pawn_is_ship2': same(self.pawn(), self.ship2), 'ship2_pilot': self.ship2.get_pilot().get_name() if self.ship2.get_pilot() else None,
                              'char_health': self.health(self.char), 'char_att': self.char.get_attach_parent_actor().get_name() if valid(self.char) and self.char.get_attach_parent_actor() else None,
                              'ship2_dead': bool(self.ship2.is_airship_dead()), 'ship2_health': self.tele(self.ship2).get('Health')}

    def end_t4_kill(self):
        p = self.D.get('post') or {}
        ok = self.D.get('pilot_ok') and not p.get('pawn_is_ship2') and p.get('ship2_pilot') is None and p.get('char_health') is not None and \
            p['char_health'] <= 0.0 and not p.get('ship2_dead')
        self.check('T4.2_pilot_killed_by_share_S', 'PASS' if ok else 'FAIL', 'pilot of ship 2 %s at %s health, Damage 100 (share 25): %s (want ejected, '
                   'then dead on foot; ship alive)' % (self.D.get('pilot_ok'), self.D.get('h_low'), p))

    # ---- T5.15 (S): a gunner killed at the gun. Its seat is inside the hull's convex hulls, so the ragdoll would start
    # inside the simulated hull (AAirshipPawn::KeepCorpseOffHull makes it ignore the hull's object type)
    def start_t5_dead(self):
        self.D['old'] = self.char

    def hull_motion(self, ship):
        h = self.hull(ship)
        return v3(h.get_physics_linear_velocity('None')), v3(h.get_physics_angular_velocity_in_degrees('None'))

    def ph_t5_dead(self, el):
        # t4_kill's on-foot death: the GameMode respawns the player RespawnDelay (5 s) later, as a new character
        if 'c' not in self.D:
            p = self.pawn()
            if valid(p) and isinstance(p, unreal.Character) and not same(p, self.D.get('old')) and (self.health(p) or 0.0) > 0.0:
                self.D['c'] = p
                self.D['c_t'] = el
                self.char = p
                self.line('INFO', 'respawned character %s at %.1f s' % (p.get_name(), el))
            return
        c, t0 = self.D['c'], self.D['c_t']
        if el >= t0 + 0.5 and 'm' not in self.D:
            self.D['m'] = True
            self.cmd('Aura.Airship.Mount 0 2')
        if el >= t0 + 1.5 and 'k' not in self.D:
            self.D['k'] = True
            ship = next((s for s in (self.ship2, self.ship) if valid(s) and same(self.gunner(s, 2), c)), None)
            self.D['ship'] = ship
            if ship is None:
                return
            v, w = self.hull_motion(ship)
            self.D['pre'] = {'v': v, 'w': w, 'char': self.char_info(c, ship)}
            mesh = gp(c, 'mesh', 'Mesh')
            self.D['mesh'] = mesh
            self.D['com0'] = v3(mesh.get_center_of_mass()) if mesh else None
            self.D['trk'] = []
            self.hurt(c, (self.health(c) or 0.0) + 50.0)
            self.D['k_t'] = el
        ship = self.D.get('ship')
        if 'k_t' in self.D and ship is not None and el <= self.D['k_t'] + 2.5:
            v, w = self.hull_motion(ship)
            mesh = self.D.get('mesh')
            com = v3(mesh.get_center_of_mass()) if valid(mesh) else None
            self.D['trk'].append((r(el - self.D['k_t'], 3), r(v, 1), r(w, 2), r(com, 0) if com else None))
            if 'resp' not in self.D and valid(mesh) and el >= self.D['k_t'] + 0.2:
                try:
                    self.D['resp'] = en(mesh.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PHYSICS_BODY))
                    self.D['sim'] = bool(mesh.is_simulating_physics('None'))
                except Exception:  # noqa: BLE001
                    self.err('t5_dead_resp')
        if 'k_t' in self.D and el >= self.D['k_t'] + 2.6 and 'post' not in self.D and ship is not None:
            self.D['post'] = {'gunner': self.gunner(ship, 2), 'att': c.get_attach_parent_actor().get_name() if valid(c) and c.get_attach_parent_actor() else None,
                              'health': self.health(c)}

    def end_t5_dead(self):
        if 'c' not in self.D:
            self.check('T5.15_dead_gunner_ragdoll_S', 'FAIL', 'no respawned character within the phase (t4_kill\'s death, RespawnDelay 5 s)')
            return
        if self.D.get('ship') is None:
            self.check('T5.15_dead_gunner_ragdoll_S', 'FAIL', 'Aura.Airship.Mount 0 2 did not put the respawned character on R1 of a living ship')
            return
        pre, post, trk = self.D.get('pre') or {}, self.D.get('post') or {}, self.D.get('trk') or []
        dv = max((dist(x[1], pre['v']) for x in trk), default=None)
        w0 = math.sqrt(sum(a * a for a in pre['w']))
        dw = max((abs(math.sqrt(sum(a * a for a in x[2])) - w0) for x in trk), default=None)
        com0 = self.D.get('com0')
        rise = max(((x[3][2] - com0[2]) for x in trk if x[3] and com0), default=None)
        ok = (self.D.get('resp') == 'ECR_IGNORE' and dv is not None and dv < 50.0 and dw is not None and dw < 2.0 and rise is not None and rise < 100.0
              and post.get('gunner') is None and post.get('att') is None and (post.get('health') or 0.0) <= 0.0)
        self.check('T5.15_dead_gunner_ragdoll_S', 'PASS' if ok else 'FAIL', 'respawned player on R1 of %s, killed there: mesh response to PhysicsBody %s '
                   '(want ECR_IGNORE), simulating %s; hull speed change max %s cm/s (want < 50), spin change max %s deg/s (want < 2); body centre '
                   'of mass rose at most %s cm (want < 100: not thrown out of the deck); after 2.6 s %s (want station free, detached, dead)' % (
                       self.D['ship'].get_name(), self.D.get('resp'), self.D.get('sim'), r(dv, 1) if dv is not None else None,
                       r(dw, 2) if dw is not None else None, r(rise, 0) if rise is not None else None, post), {'track': trk[::3], 'pre': pre})


def write_r2_report(R):
    try:
        L = ['%s  armed %s  reason: %s  game %.1f s  wall %s s' % (R['version'], R['armed_utc'], R.get('reason'), R.get('game_t', 0), R.get('wall_s')),
             'cfg %s' % R.get('cfg'), 'setup %s' % json.dumps(R.get('setup'), default=str), '']
        cnt = {}
        for k, c in R['checks'].items():
            cnt[c['status']] = cnt.get(c['status'], 0) + 1
        L.append('checks: %s' % cnt)
        for k, c in R['checks'].items():
            L.append('%-5s %-34s %s' % (c['status'], k, c['summary']))
        L.append('')
        L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        for k, v in R['errors'].items():
            L.append('--- %s\n%s' % (k, v['last'][-900:]))
        ls = R.get('log_scan') or {}
        L.append('log: %s' % dict((k, v['count']) for k, v in ls.items()))
        L.append('captures: %s' % [s['file'] for s in R.get('shots', [])])
        with open(os.path.join(R2DIR, 'r2_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        pass


_old59 = globals().get('AS59_RUN')
if _old59 is not None and _old59.phase not in ('finished',):
    print('an as_59 run is active (phase %s): stop it first (as_59x_stop.py)' % _old59.phase)
else:
    AS59_RUN = R2Run()
    _ok59 = AS59_RUN.arm()
    for _l in AS59_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_59s_status.py; results in Saved/Airship/round2/)' if _ok59 else 'FAIL: not armed'))
