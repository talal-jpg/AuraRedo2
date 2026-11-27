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
#  t2_ray 5     a test ball parked on the camera ray (2 s     T2.9 the cannons' aim targets don't move (< 0.3 deg)
#               settling first, baseline spread < 0.1 deg)
#  t2_far 7.5   ship 300 m from the port wall's back face     T2.4 elevation at the 8.5 deg cap, the ball lands short
#  t2_lead 7.5  30 m/s along +X, aim 15 m ahead of the beam   T2.3 impact within 6 m (velocity lead); 2.5 s of flight
#               before the shot, the aim compensates the camera's rotation lag (aim_at lag_comp)
#  t4_crew 2.5  Aura.Airship.Damage 100 with the pilot aboard T4.1 (S) pilot -25
#  t9_rest 32   F exit at rest                                T4.4 (S) health kept at exit; T9.3 Hold, < 0.5 m in 30 s
#  t5_cannon 5.5 Mount 0 2 (R1), StationFire twice, Board, Dismount  T5.9 / T5.14 / T5.4 / T5.10 / T5.8 (S)
#  t6_hit 4     ship 2 60 m ahead, TurretFire 1 s             T6.4 ship 2 -80 +-25 %; T6.8 per bullet = 4 x the GE value
#  t6_turret 3  TurretFire 1 s at ship 2's port turret        T6.9 that turret loses health in whole bullets (the first
#                                                            Visibility hit on the line is reported: the HitBox itself
#                                                            since the hull's collision ignores Visibility, or a PA box
#                                                            in front of it, which FindTurretBehindHullHit hands on)
#  t6_own 3.5   rider on the forward deck, TurretFire at it   T6.5 rider and ship unchanged
#  t5_turret 10 Mount 0 4 (TurretL), StationFire 1 s, 3.5 s   T5.6 / T5.7 (S) 9-11 shots, heat ~0.33, overheat ~3 s
#  t6_destroy 3.5 TurretDamage 0 400 with the gunner on it    T6.6 (S) wreck, fire FX, gunner ejected, no more shots
#  t3_bullets 7 Aura.MechSentinel.TestBullet x3               T3.1 hull -3 (the line meets a PA_Airship box in the hull's
#                                                            side: the hull's collision ignores Visibility since the
#                                                            helm / deck change), T3.2 turret -3, ship unchanged (a real
#                                                            line from outboard: it reaches the HitBox directly now, the
#                                                            redirect stays as a fallback), T3.3 on-foot -3
#  t2_gun <=16  a test ball (ship 2's) 1 m off ship 1's port side, the player on ship 1's deck shoots it with GA_GunShoot
#               (ends 1 s after the shoot-down)
#                                                            T2.6 -1 per hit, shot down after 30, no splash
#  t2_splash 4  a test ball (ship 2's) into TEMP_AS59_SplashPost, the player 5.5 m from the impact
#                                                            T2.5 (character dummy) 60 x lerp(1, 0.3, d / 600) +-15 %
#  t8_below 6   the player on the ground under the hull, F    T8.1 (S) F does nothing 7 m and 12 m under the belly (Talal
#                                                            11-25: no boarding from below, BoardBelowDistance 0)
#  t8_helm 8    the player on the planks 2.5 m behind the     T8.2 F there does not take the helm; T8.3 F at the wheel does;
#               wheel, then at the wheel: F, F again (exit)   T8.4 leaving keeps the place (hull-space xy within 10 cm of
#                                                            the driving pose), walking, feet on the deck boxes, based on
#                                                            the ship; T8.6 Visibility traces from above and from port
#                                                            meet the player first (the UCX lid over the planks no
#                                                            longer blocks), then the Mesh's deck box
#  t8_walk 15   Classic, Aura.Airship.Input 1 0, a turn, a    T8.5 a walker on the planks is carried: walking, a rider, on
#               jump at speed                                 the deck, within 1 m of its spot; T8.7 a jump at speed
#                                                            lands back on the deck (the base's velocity is inherited);
#                                                            T8.8 no slide after that landing (<= 50 cm in 1.5 s); T8.9 a
#                                                            second jump + the air jump with input to starboard keeps
#                                                            the ship's speed (only the relative velocity turns)
#  t8_reach 12  opt-in only (AS59_ONLY="t8_reach"), INFO      T8.R1 jump / jump + air jump heights on the main deck;
#               the parked ship                              T8.R2 F under the port turret's seat from the main deck,
#                                                            standing and at the top of a jump
#  t8_boost <=75 opt-in only (AS59_ONLY="t8_boost"), INFO     T8.B1 from the ground 15 m to port of the parked ship's helm
#               the player's own keys, nothing teleported     with Shift + W (GA_BoostBP) and the view: how high, how
#               after the start                              fast, the mana it costs, on the planks or not, then W to
#                                                            the wheel and F; T8.B2 Space, Space, Space with W held
#                                                            (GA_JumpHover: jump, air jump, hover): the rise and the
#                                                            level gap crossed
#  t2_own 13    L1's muzzle 1 m from the port wall            T2.8 the ship's own balls burst inside their splash radius
#                                                            of a deck rider, of L1's gunner and (a real broadside) of
#                                                            the hull with the pilot aboard: no health lost
#  t8_lid 5     SetDeckOnPhysicsAsset(false) on ship 1        T8.11 F at the wheel takes the helm on a ship whose deck
#                                                            is the hull's collision (no physics asset bodies)
#  t8_gone 9    a third ship, piloted, then destroyed         T8.12 a ship that goes away under its pilot throws him
#               (Aura.Airship.Spawn, K2_DestroyActor)         clear (not left walking where the wheel was)
#  t9_drift_<s> 41 per scheme: 48 m/s, F exit                 T9.1 / T9.2 Drift, 2.5 +-0.3 m/s by 30 s, heading within
#                                                            2 deg, no reverse (from 3 s after the exit); T9.5 board
#                                                            while drifting: None, throttle
#  t9_wall 25   drifting at the port wall                     T9.4 stops >= 0.5 m short or on contact, no damage, Hold
#  t9_input <=75 Aura.Airship.Input 1 0 (ship 2 cleared at   T9.6 None while active, Coast, Hold below 3 m/s (~39 s of
#               once), then InputClear; ends 2 s after Hold   coast from 48 m/s)
#  t7_caps 4    pilot at the helm                             T7.2 wheel 136-144 cm (part_bounds.json) + captures; T7.3
#  t5_kill 3    gunner on R2, ship 1 killed (crew share 0     T5.11 (S) gunner ejected alive
#               for the phase: D4 would give him 25 % of the whole health and kill him)
#  t4_kill 5    pilot of ship 2 at 10 health, Damage 100      T4.2 (S) pilot ejected, then dead; ship alive
#  t5_dead 12   the respawned player mans R1 of ship 2, killed T5.15 (S) simulating parts ignore the hull (the mech has
#               there                                          none), no kick (hull spin and speed unchanged), body not
#                                                            thrown up after the dismount placed it, station free
#  end          log scan                                      T10.1 every new console command ran and logged
# Not here (listen server or not in L_AirshipTest): T2.7, T3.4, T3.5, T4.3, T4.5, T5.1-T5.5, T5.12, T5.13, T6.2,
# T6.3, T6.7, T7.1 (Blender), T9.7; they are listed as SKIP in the report with the reason.
# PIE run 2026-11-25 (run_r2_pie.sh): 44 PASS, 0 FAIL after harness fixes, Docs/Airship/round2/NOTES_assets.md.
# 2026-11-27 (Talal 11-25, helm and deck; SPEC_A.md 6.8; not run in PIE yet): deck_point traces the deck the characters
# walk on (the Mesh's physics asset, AAirshipPawn::IsDeckOnPhysicsAsset) instead of the top of the hull's collision; T3.1
# keeps the Mesh's collision on (the PA bodies are the Visibility target now); T8.1 turned around; t8_helm / t8_walk new.
# PIE run 2026-11-27 (PA_Airship rebuilt with the 96 hull boxes, hull ink applied): 52 PASS, 0 FAIL, 4 INFO, 14 SKIP.
# First run 49 PASS / 1 FAIL: T8.1's second case traced the ground through the player left there by the first case
# (measurement, fixed). T8.7's numbers showed the walker 1.6 m forward of its landing point, at the wheel: T8.8 / T8.9
# were added and UMyCharacterMovementComponent changed (CPP_NOTES.md 15.10). T5.16a/b (INFO) + two captures: the gunners'
# feet over the deck at a cannon and at a turret.
# PIE run 2026-11-28 (second review, SPEC_A.md 6.9; PA_Airship with the closed seams and the 7 deck prop boxes): 55 PASS,
# 0 FAIL, 4 INFO, 13 SKIP. New: t2_own (T2.8), t8_lid (T8.11), t8_gone (T8.12), three T1.3 frames from the new camera
# and the pilot's view; opt-in t8_boost (T8.B1 / T8.B2: from the ground to the helm with the game's own keys). T5.17 /
# t5_deck of the first pass is gone again with the C++ setting it tested.
import json, math, os, time, traceback  # unreal = inbox namespace

AS59_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as59_src = open(AS59_AS30).read()
exec(compile(_as59_src[:_as59_src.index('\nclass AsRun')], AS59_AS30, 'exec'), globals())   # OUT, MAP_NAME, v3, r, dist, tl_get/tl_set, gp, valid, find_log

AS59_VERSION = 'as_59_pie_round2 2026-11-27 helm+deck, review fixes'
R2DIR = os.path.join(OUT, 'round2')
CAPS2 = os.path.join(OUT, 'captures', 'round2')
TEMP59 = 'TEMP_AS59_'
IA = '/Game/Assets/MyShip/Drivable/Input/'
IA_LMB_PATH = '/Game/Level/PlayerInput/IA_LMB'
SETTINGS_CLS = '/Script/Aura.AirshipSettings'
BALL_BP = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C'
GE_GUN = '/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C'
GC_GUN_BURST = '/Game/Level/GAS/GameplayCues/GC_BurstActor_GunShoot.GC_BurstActor_GunShoot_C'
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
SKIPPED = {'T2.7': 'listen server (client copy of a shot-down ball)',
           'T3.4': 'L_AirshipTest has no untagged GAS enemy', 'T3.5': 'L_AirshipTest has no swarm spawner',
           'T4.3': 'listen server (a second player as gunner at 10 health)',
           'T4.5': 'needs ship 2 piloted (a real broadside) while ship 1\'s L1 is manned: 2 players at once; as_60 does not drive it either',
           'T5.1-T5.5': 'listen server (client F / aim / LMB / broadside)', 'T5.12': 'listen server', 'T5.13': 'listen server',
           'T6.2': 'listen server (client pilot LMB in the bow arc)', 'T6.3': 'listen server', 'T6.7': 'no swarm in L_AirshipTest',
           'T7.1': 'Blender (rig_all.sh / verify_all.sh), not PIE', 'T9.7': 'listen server'}


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


HIT_INFO_ERR = []      # the first failure of each way hit_info reads a HitResult (in the report: a silent miss hid it before)


def hit_info(res):
    """(blocking, impact point list, actor, component) of a line trace result (HitResult, tuple or None). Reads the
    HitResult with GameplayStatics.break_hit_result, else HitResult.to_tuple(), else its properties; each failure is
    recorded once in HIT_INFO_ERR (a failure used to read as 'no hit')."""
    if res is None:
        return False, None, None, None
    hit = res
    if isinstance(res, tuple):
        hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
        if hit is None:
            return False, None, None, None
    t = None
    for how in ('break', 'to_tuple'):
        try:
            t = tuple(unreal.GameplayStatics.break_hit_result(hit)) if how == 'break' else tuple(hit.to_tuple())
            break
        except Exception:  # noqa: BLE001
            if len(HIT_INFO_ERR) < 4:
                HIT_INFO_ERR.append('%s: %s' % (how, traceback.format_exc().strip().splitlines()[-1]))
    if t is not None:
        bools = [x for x in t if isinstance(x, bool)]
        vecs = [x for x in t if isinstance(x, unreal.Vector)]
        act = next((x for x in t if isinstance(x, unreal.Actor)), None)
        comp = next((x for x in t if isinstance(x, unreal.PrimitiveComponent)), None)
        if comp is not None and act is None:
            try:
                act = comp.get_owner()
            except Exception:  # noqa: BLE001
                pass
        imp = v3(vecs[1]) if len(vecs) > 1 else (v3(vecs[0]) if vecs else None)
        return (bools[0] if bools else False), imp, act, comp
    try:
        comp = hit.get_editor_property('component')
        act = comp.get_owner() if comp else None
        return bool(hit.get_editor_property('blocking_hit')), v3(hit.get_editor_property('impact_point')), act, comp
    except Exception:  # noqa: BLE001
        if len(HIT_INFO_ERR) < 4:
            HIT_INFO_ERR.append('props: %s' % traceback.format_exc().strip().splitlines()[-1])
        return False, None, None, None


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
        self.prev_v = {}
        self.attrs = {}
        for n in ('Health', 'MaxHealth', 'Mana'):
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
        ph = [('settle', 3.0), ('spawn2', 3.0), ('board', 2.5), ('t1_port', 5.0), ('t1_cap0', 3.5), ('t2_ray', 5.0),
              ('t2_far', 7.5), ('t2_lead', 7.5), ('t4_crew', 2.5), ('t9_rest', 32.0), ('t5_cannon', 5.5), ('t6_hit', 4.0),
              ('t6_turret', 3.0), ('t6_own', 3.5), ('t5_turret', 10.0), ('t6_destroy', 3.5), ('t3_bullets', 7.0), ('t2_gun', 16.0),
              ('t2_splash', 4.0), ('t2_own', 13.0), ('t8_below', 6.0), ('t8_helm', 8.0), ('t8_walk', 15.0), ('t8_lid', 5.0),
              ('t8_gone', 9.0)]
        for s in self.cfg['drift_schemes']:
            ph.append(('t9_drift_%d' % s, 41.0))
        ph += [('t9_wall', 25.0), ('t9_input', 75.0), ('t7_caps', 4.0), ('t5_kill', 3.0), ('t4_kill', 5.0), ('t5_dead', 12.0)]
        only = self.cfg.get('only')
        if only and any(o.startswith('t8_reach') for o in only):
            ph.append(('t8_reach', 12.0))      # opt-in measurement (INFO only), never part of the full run
        if only and any(o.startswith('t8_boost') for o in only):
            ph.append(('t8_boost', 75.0))      # opt-in measurement (INFO only): ends itself
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
        for n in ('IA_AirshipFire', 'IA_AirshipBoard', 'IA_AirshipExit', 'IA_AirshipLook'):
            self.act[n] = unreal.load_asset(IA + n)
        self.act['IA_LMB'] = unreal.load_asset(IA_LMB_PATH)
        for n in ('IA_Shift', 'IA_Move'):       # the on-foot boost (GA_BoostBP, Input.Shift) and walking
            self.act[n] = unreal.load_asset(IA_LMB_PATH.rsplit('/', 1)[0] + '/' + n)
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
        self.R['hit_info_err'] = list(HIT_INFO_ERR)
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
                if c == 'Aura.Airship.Telemetry':
                    # Telemetry logs per ship without its own name: '<ship>: speed .. m/s (fwd ..' is its first line
                    lg = [l for l in lines if 'LogAirship:' in l and ': speed ' in l and 'm/s (fwd' in l]
                else:
                    lg = [l for l in lines if c in l and 'Command not recognized' not in l]
                res[c] = 'ok (%d log lines)' % len(lg) if lg and not nr else ('NOT RECOGNISED' if nr else 'no log line')
            # Telemetry's round-2 line (the third per ship): '<ship>: unpiloted N (drift .. hold ..), stations 0x.. gunners .. turrets [..]'
            tl = [l for l in lines if 'LogAirship:' in l and ': unpiloted ' in l and 'stations 0x' in l and 'turrets [' in l]
            res['Telemetry line 3'] = 'ok: %s' % tl[0][:220] if tl else 'no telemetry line with unpiloted / stations / turrets'
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

    def deck_comp(self, ship):
        """what characters stand on and Visibility traces hit: the Mesh (PA_Airship's boxes, tops at the planks) when the
        ship says so (AAirshipPawn::IsDeckOnPhysicsAsset, Talal 11-25), else the hull's collision (v1: the UCX lid)."""
        try:
            if bool(call(ship, 'is_deck_on_physics_asset')):
                return ship.get_editor_property('Mesh')
        except Exception:  # noqa: BLE001
            self.err('deck_comp')
        return self.hull(ship)

    def rel(self, ship, p):
        """hull-space (= the ship's root) location of the world point p"""
        return v3(unreal.MathLibrary.inverse_transform_location(ship.get_actor_transform(), unreal.Vector(*p)))

    def deck_hit(self, ship, hx, hy, z_hi=1600.0, z_lo=-200.0):
        """world point of the first deck surface (deck_comp: a line trace on that component alone, every body of the
        physics asset) under hull-space (hx, hy, z_hi), down to z_lo; None without one."""
        tr = ship.get_actor_transform()
        top = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, z_hi))
        bot = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, z_lo))
        res = self.deck_comp(ship).line_trace_component(top, bot, False, False, False)
        if isinstance(res, tuple):
            if not (isinstance(res[0], bool) and not res[0]):
                return next((v3(x) for x in res if isinstance(x, unreal.Vector)), None)
        return None

    def char_hh(self):
        caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
        return float(caps.get_scaled_capsule_half_height()) if caps else 90.0

    def deck_point(self, ship, hx, hy):
        """world point on the deck (deck_hit: the planks' boxes, or whatever part box stands over that spot) at hull-space
        (hx, hy), plus the character's half height + 30 cm."""
        hit = self.deck_hit(ship, hx, hy)
        p = hit if hit is not None else v3(unreal.MathLibrary.transform_location(ship.get_actor_transform(), unreal.Vector(hx, hy, 700.0)))
        return [p[0], p[1], p[2] + self.char_hh() + 30.0], hit is not None

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

    def aim_at(self, point, lag_comp=False):
        """Points the view (the camera manager's rotation: what the pilot's aim trace and the gun's crosshair use) at point:
        the control rotation is the look-at from the camera. lag_comp (a moving view: t2_lead's ship at 30 m/s, the on-foot
        gun camera in t2_gun) adds the camera's current lag behind the control rotation (spring-arm rotation lag; at 30 m/s
        120 m from the target the look-at turns ~14 deg/s and a plain set left the crosshair 9 m ahead of the aim point):
        an integral step (gain 1) on the view's error, the lag term capped at 15 deg. On a still view it makes the camera
        hunt by ~0.3 deg, so the still aim phases use the plain set. Returns the view's error (yaw, pitch deg) before this
        frame's set."""
        try:
            loc, rot = self.cam()
            want = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(*point))
            lag_y = lag_p = 0.0
            if lag_comp:
                ctrl = self.pc.get_control_rotation()
                lag_y = max(-15.0, min(15.0, wrap180(ctrl.yaw - rot.yaw)))
                lag_p = max(-15.0, min(15.0, wrap180(ctrl.pitch - rot.pitch)))
            self.pc.set_control_rotation(unreal.Rotator(0.0, wrap180(want.pitch + lag_p), wrap180(want.yaw + lag_y)))
            # A pilot who aims moves the mouse: a tiny look input each frame (0.01) keeps the ship's camera recenter
            # (Classic: after RecenterDelay 1.5 s without look input above 8 m/s, the camera eases back behind the ship at
            # RecenterSpeed 2/s) from pulling the crosshair off a harness-set aim (t2_lead flies 30 m/s)
            if valid(self.ship) and same(self.pawn(), self.ship):
                self.inject('IA_AirshipLook', 0.01)
            return r(wrap180(want.yaw - rot.yaw), 3), r(wrap180(want.pitch - rot.pitch), 3)
        except Exception:  # noqa: BLE001
            self.err('aim_at')
            return None

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

    def track_muzzle(self):
        """after a broadside: game time the first NS_AirshipMuzzle component shows and the time none is left (the smoke's
        measured life; components that existed before the shot are left out)."""
        if 'fire_t' not in self.D or self.D.get('mz_gone') is not None:
            return
        n = len([c for c in self.muzzle_comps(self.ship) if c not in self.D.get('mz_old', set())])
        if n and self.D.get('mz_first') is None:
            self.D['mz_first'] = self.now
        if not n and self.D.get('mz_first') is not None:
            self.D['mz_gone'] = self.now
        self.D['mz_max'] = max(self.D.get('mz_max', 0), n)

    def smoke_life(self):
        a, b = self.D.get('mz_first'), self.D.get('mz_gone')
        return {'components_max': self.D.get('mz_max'), 'first_after_input_s': r(a - self.D['fire_t'], 3) if a is not None and 'fire_t' in self.D else None,
                'life_s': r(b - a, 3) if a is not None and b is not None else None}

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
                        # The velocity the ball inherited is the ship's at the shot, before the broadside's recoil kick
                        # (CannonRecoilImpulseDV per cannon, applied in the same frame): the last frame's sample. The
                        # velocity now (after the kick) is kept for the record.
                        rec['ship_v_after'] = r(v3(src.get_velocity()), 1) if src else None
                        rec['ship_v'] = (self.prev_v.get(src.get_name()) or rec['ship_v_after']) if src else None
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

    def cross_y(self, b, y):
        """where the ball's sampled path crosses the plane y (linear between samples), or None."""
        pts = b.get('path') or []
        for i in range(len(pts) - 1):
            a, c = pts[i][1:], pts[i + 1][1:]
            if (a[1] - y) * (c[1] - y) <= 0.0 and a[1] != c[1]:
                f = (y - a[1]) / (c[1] - a[1])
                return r([a[k] + f * (c[k] - a[k]) for k in range(3)], 1)
        return None

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
                         'bow': ((1200.0, -1400.0, 1300.0), (2300.0, 0.0, 700.0)),
                         'cannonR1': ((350.0, 1500.0, 650.0), (-45.0, 640.0, 310.0)),      # the gunner beside R1's breech
                         'turret0': ((1500.0, -900.0, 900.0), (2030.0, -245.0, 740.0)),    # the gunner behind the port turret
                         'turret1': ((1500.0, 900.0, 900.0), (2030.0, 245.0, 740.0)),      # ... behind the starboard turret
                         # T1.3: from off the port bow along the hull's side, aft: L1's muzzle 7.5 m and L2's 18.5 m away,
                         # the smoke they blow outboard against the sky (the old 'port' view had it on the white hull)
                         'muzzle': ((700.0, -900.0, 420.0), (-1143.0, -760.0, 360.0))}
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
        for _s in (self.ship, self.ship2):
            try:
                if valid(_s):
                    self.prev_v[_s.get_name()] = r(v3(_s.get_velocity()), 1)
            except Exception:  # noqa: BLE001
                pass
        self.sample()
        el = self.now - self.p_t0
        ph = self.phase
        base = 't9_drift' if ph.startswith('t9_drift_') else ph
        try:
            getattr(self, 'ph_' + base, lambda e: None)(el)
        except Exception:  # noqa: BLE001
            self.err('ph_' + ph)
        # a phase ends at its length, or earlier once its measurement is complete (D['phase_done'], adaptive phases)
        if el >= self.phases[self.pi][1] or self.D.get('phase_done'):
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
        # T1.3 (read 2026-11-28): what the side camera shows differs between editor sessions on the same build. Final
        # run: orange-brown puffs at both muzzles at 0.1 s, nothing at 0.3 s and 1.2 s. One session (11-27 13:54 UTC): a
        # large grey cloud at 0.3 s. Two short runs: only sparks at 0.1 s. Never smoke at 1.2 s. Ruled out, one run each:
        # Niagara's visibility culling (fx.Niagara.Scalability.VisibilityCulling 0) and spawning the effect once out of
        # view 1.8 s before the shot. Particle counts cannot be read from Python in 5.8. Not tried: a second broadside.
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
        self.track_muzzle()
        dt = self.now - self.D['fire_t']
        if dt >= 0.1 and 'cap01' not in self.D:
            self.D['cap01'] = True
            self.capture('t1_muzzle_0.1s', 'muzzle', self.ship)
        if dt >= 0.16 and 'cap02' not in self.D:
            self.D['cap02'] = True
            self.capture('t1_muzzle_0.2s_pilot', 'player', self.ship)      # what the pilot's own camera shows
        if dt >= 0.3 and 'mz03' not in self.D:
            self.D['mz03'] = [c for c in self.muzzle_comps(self.ship) if c not in self.D['mz_old']]
            self.capture('t1_muzzle_0.3s', 'muzzle', self.ship)
        if dt >= 1.2 and 'cap12' not in self.D:
            self.D['cap12'] = True
            self.capture('t1_muzzle_1.2s', 'muzzle', self.ship)
        if dt >= 1.5 and 'mz15' not in self.D:
            self.D['mz15'] = self.muzzle_comps(self.ship)

    def end_t1_port(self):
        mz03, mz15 = self.D.get('mz03') or [], self.D.get('mz15')
        self.check('T1.1_muzzle_lifetime', 'PASS' if len(mz03) >= 2 and mz15 == [] else 'FAIL',
                   'port broadside: NS_AirshipMuzzle components under the Mesh %d at +0.3 s (want >= 2), %s at +1.5 s (want 0)%s; measured smoke '
                   'life %s' % (len(mz03), None if mz15 is None else len(mz15), ' FALLBACK RequestFire' if self.D.get('fb') else '', self.smoke_life()),
                   {'at_0.3': mz03, 'at_1.5': mz15, 'smoke': self.smoke_life()})
        caps = [s['file'] for s in self.R['shots'] if s['label'].startswith('t1_muzzle')]
        self.check('T1.3_muzzle_captures', 'INFO' if len(caps) == 4 else 'WARN', 'captures to look at, 0.1 s, 0.3 s and 1.2 s after the port '
                   'broadside, from off the port bow along the hull\'s side (the muzzles of L1 and L2 with the sky behind what they blow out), '
                   'and the pilot\'s own view at 0.2 s. '
                   'This line does not read the pictures and does not show that smoke is visible; T1.1 (the effect\'s components and their '
                   'life) is the measured part: %s' % caps)
        bs = [b for _, b in self.balls_since(self.D.get('fire_t', 1e9), 't1_port')]
        props, okp = [], len(bs) == 2
        for b in bs:
            rel = [b['v0'][i] - (b.get('ship_v') or [0, 0, 0])[i] for i in range(3)]
            spd = math.sqrt(sum(x * x for x in rel))
            props.append({'radius': b.get('radius'), 'mesh_scale': b.get('mesh_scale'), 'gravity': b.get('gravity'), 'launch_cms': r(spd, 1),
                          'ship_v_at_shot': b.get('ship_v'), 'ship_v_after_recoil': b.get('ship_v_after')})
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
        self.track_muzzle()
        if self.now - self.D['fire_t'] >= 1.2 and 'mz12' not in self.D:
            self.D['mz12'] = self.muzzle_comps(self.ship)

    def end_t1_cap0(self):
        orig = (self.orig.get('settings') or {}).get('MuzzleFXMaxSeconds', 1.0)
        self.cmd('Aura.Airship.Set Settings.MuzzleFXMaxSeconds %s' % orig)
        mz = self.D.get('mz12')
        self.check('T1.2_muzzle_asset_alone', 'PASS' if mz == [] else 'FAIL', 'MuzzleFXMaxSeconds 0 (no C++ cap), stbd broadside: %s NS_AirshipMuzzle '
                   'components at +1.2 s (want 0); measured smoke life without the cap %s' % (None if mz is None else len(mz), self.smoke_life()),
                   {'at_1.2': mz, 'smoke': self.smoke_life()})

    # ---- T2.9: a ball on the camera ray doesn't pull the aim
    def start_t2_ray(self):
        self.D['before'], self.D['after'] = [], []

    def aim_vals(self):
        return self.anim(self.ship, ['CannonYawDeg_L1', 'CannonElevDeg_L1', 'CannonYawDeg_L2', 'CannonElevDeg_L2'])

    def ph_t2_ray(self, el):
        # The camera swings from t1_cap0's starboard aim to the port wall: its rotation lag and the cannons' slew (45 deg/s,
        # elevation settling) need time, so the baseline is read once they are still (2.0-2.5 s); the ball goes on the ray
        # at 2.5 s; 'after' is 3.0-3.5 s (a pulled aim point would swing the cannons by several degrees in that time)
        A = self.D_A()
        self.aim_at(A)
        if el < 2.5 and int(el * 10) != self.D.get('_k'):
            self.D['_k'] = int(el * 10)
            self.D.setdefault('settle', []).append((r(el, 2), self.aim_vals()))
        if 2.0 <= el < 2.5:
            self.D['before'].append(self.aim_vals())
            if 'ray0' not in self.D:
                ok, imp, act, _ = self.cam_ray(ignore=[self.ship])
                self.D['ray0'] = {'hit': ok, 'actor': act.get_name() if act else None, 'at': r(imp, 0) if imp else None,
                                  'off_A_cm': r(dist(imp, A), 0) if imp else None}
        if el >= 2.5 and 'ball' not in self.D:
            loc, rot = self.cam()
            p = v3(loc + unreal.MathLibrary.get_forward_vector(rot) * 4000.0)
            self.D['ball'] = self.spawn_ball(p, (0.0, 0.0, 0.0), None, 0.0, 0.0)
            self.D['ball_at'] = r(p, 0)
        if 2.6 <= el < 2.8 and 'ray' not in self.D:
            ok, imp, act, _ = self.cam_ray(ignore=[self.ship])
            self.D['ray'] = {'hit': ok, 'actor': act.get_name() if act else None, 'at': r(imp, 0) if imp else None}
        if 3.0 <= el < 3.5:
            self.D['after'].append(self.aim_vals())
        if el >= 4.0 and self.D.get('ball') is not None and not self.D.get('gone'):
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
        ch, spread = {}, {}
        for k in ('CannonYawDeg_L1', 'CannonElevDeg_L1', 'CannonYawDeg_L2', 'CannonElevDeg_L2'):
            xs = [x[k] for x in self.D['before'] if x.get(k) is not None]
            a = mean(xs)
            b = mean([x[k] for x in self.D['after'] if x.get(k) is not None])
            ch[k] = r(b - a, 3) if a is not None and b is not None else None
            spread[k] = r(max(xs) - min(xs), 3) if xs else None
        on_ray = (self.D.get('ray') or {}).get('actor') and 'annonball' in str((self.D.get('ray') or {}).get('actor'))
        settled = all(v is not None and v < 0.1 for v in spread.values())
        ok = all(v is not None and abs(v) < 0.3 for v in ch.values())
        st = ('PASS' if ok else 'FAIL') if (on_ray and settled) else 'WARN'
        self.check('T2.9_aim_ignores_balls', st, 'test ball parked on the camera ray at %s (Python camera trace hits %s; before the ball it hit %s): '
                   'cannon aim change %s deg (want < 0.3); baseline spread over 0.5 s %s deg (want < 0.1: settled)%s' % (
                       self.D.get('ball_at'), self.D.get('ray'), self.D.get('ray0'), ch, spread,
                       '' if settled else ' NOT SETTLED: the test proves nothing'),
                   {'change': ch, 'spread': spread, 'ray': self.D.get('ray'), 'ray0': self.D.get('ray0'), 'settle': self.D.get('settle')})

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
        # 2.5 s of steady flight before the shot: the camera swings ~180 deg from t2_far's starboard aim and the ship has
        # just been teleported 430 m (boom position / rotation lag), so the crosshair needs time to settle on A
        self.D['FT'] = 2.5
        self.D['x0'] = x_fire - 3000.0 * self.D['FT']
        self.D['A'] = A
        self.D['y'] = y
        self.D['cam'] = []
        self.teleport(self.ship, (self.D['x0'], y, SPAWN[2]), 0.0, (3000.0, 0.0, 0.0))

    def ph_t2_lead(self, el):
        if 'fire_t' not in self.D:
            self.hull(self.ship).set_physics_linear_velocity(unreal.Vector(3000.0, 0.0, 0.0), False, 'None')
            self.D['verr'] = self.aim_at(self.D['A'], lag_comp=True)
            if el >= self.D['FT'] - 0.5 and int(el * 10) != self.D.get('_k'):
                # where the crosshair is (the pilot's aim trace sees the same camera ray), 0.5 s before the shot and at it
                self.D['_k'] = int(el * 10)
                ok, imp, act, _ = self.cam_ray(ignore=[self.ship])
                self.D['cam'].append({'el': r(el, 2), 'hit': ok, 'actor': act.get_name() if act else None, 'at': r(imp, 0) if imp else None,
                                      'off_A_cm': r(dist(imp, self.D['A']), 0) if imp else None, 'aim': self.aim_vals(), 'view_err': self.D.get('verr')})
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
            xw = self.cross_y(b, A[1] + 50.0)
            res.append({'impact': imp, 'off_cm': r(d, 1) if d is not None else None, 'at_wall_plane': xw,
                        'wall_plane_off_cm': r(dist(xw, A), 0) if xw else None})
            ok = ok and d is not None and d <= 600.0
        self.check('T2.3_lead_30ms', 'PASS' if ok else 'FAIL', 'ship at %s cm/s (x %s at the shot), aim %s, 120 m off the beam, 15 m ahead (an aim '
                   'abeam would need 24 deg of lead, past the 20 deg yaw limit): balls %s (want within 6 m); crosshair at the shot %s' % (
                       self.D.get('v_fire'), self.D.get('x_fire'), r(A, 0), res, (self.D.get('cam') or [None])[-1]),
                   {'res': res, 'crosshair': self.D.get('cam'), 'balls': [dict((k, b.get(k)) for k in ('first', 'v0', 'ship_v', 'ship_v_after')) for b in bs]})
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
            rel = self.char_rel()
            self.check('T5.16a_gunner_R1_pose', 'INFO', 'gunner at cannon R1: hull %s, feet %s cm over the deck box at hull z %s' % (
                (r(rel, 1),) + tuple(self.feet_over_deck(rel))))
            self.capture('t5_gunner', 'cannonR1', self.ship)
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

    # ---- T6.9: turret rounds at an enemy turret. Until the helm / deck change (Talal 11-25) the line met that ship's hull
    # collision first (the turret sat inside its forward deck convex); the hull ignores Visibility now, so the rounds reach
    # the HitBox directly, or a PA_Airship box in front of it (the redirect then hands them on, as before)
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
        self.check('T6.9_turret_through_hull', 'PASS' if ok else 'FAIL', 'TurretFire 1 s from ship 1 at ship 2\'s port turret HitBox %s: '
                   'first Visibility hit from ship 1\'s muzzle %s (the turret itself, or ship 2\'s Mesh: a PA_Airship box in front of it; the '
                   'hull\'s collision ignores Visibility); turret %s -> %s (drop %s = %s bullets of %.2f, want > 0 whole bullets); ship 2 %s -> %s '
                   '(the spread\'s misses hit its boxes); %d shots' % (r(self.D.get('P'), 0), self.D.get('line'), h0[0], h1[0], drop, r(hits, 2) if hits is not None else None,
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
            rel = self.char_rel()
            fod = self.feet_over_deck(rel)
            if fod[0] is None:   # the seat (x 2000) is over the 10 cm seam between two 2 m deck slabs (1995 | 2005): beside it
                fod = self.feet_over_deck([rel[0] - 20.0, rel[1], rel[2]])
            self.check('T5.16b_gunner_turret_pose', 'INFO', 'gunner at the port turret: hull %s, feet %s cm over the deck box at hull z %s' % (
                (r(rel, 1),) + tuple(fod)))
            self.capture('t5_gunner', 'turret0', self.ship)
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
        # Since the helm / deck change (Talal 11-25) the hull's collision ignores Visibility and the Mesh's physics asset
        # bodies (PA_Airship) are what a bullet's Visibility line meets: the Mesh's collision stays ON (until then T3.1
        # turned it off to prove the hull alone took the hit; that would leave nothing to hit now)
        self.teleport(self.ship, SPAWN, 0.0)
        self.tp_char(CHAR_FOOT, 0.0)

    def bullet(self, frm, to, key):
        self.D[key + '_trace'] = self.trace(frm, to)
        self.cmd('Aura.MechSentinel.TestBullet %.0f %.0f %.0f %.0f %.0f %.0f 3' % (tuple(frm) + tuple(to)))

    def ph_t3_bullets(self, el):
        if el >= 0.5 and 'b1' not in self.D:
            self.D['b1'] = True
            self.D['h1'] = self.tele(self.ship).get('Health')
            # at the hull's port side, 1 m above the hull origin: below the planks (2.4 m there), inside the hull tub's boxes
            # (|y| < 8 m at x 0), clear of the pods (x 0.9 m on)
            to = v3(self.ship.get_actor_location())
            to[2] += 100.0
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
            # The hull's collision ignores Visibility now (the turret sits inside its forward deck convex, UCX_01): the line
            # reaches the HitBox directly. The swarm's redirect (AAirshipPawn::RedirectBulletHitToTurret) stays for a line
            # that meets a PA box first.
            self.bullet(frm, to, 'b2')
        if el >= 3.8 and 'r2' not in self.D and self.D.get('t') is not None:
            self.D['r2'] = (self.tstate(self.D['t']).get('health'), self.tele(self.ship).get('Health'))
        if el >= 4.2 and 'b3' not in self.D:
            self.D['b3'] = True
            self.D['h3'] = self.health(self.char)
            to = v3(self.char.get_actor_location())
            frm = [to[0], to[1] - 2500.0, to[2]]
            self.bullet(frm, to, 'b3')
        if el >= 6.0 and 'r3' not in self.D:
            self.D['r3'] = self.health(self.char)

    def end_t3_bullets(self):
        h1, r1 = self.D.get('h1'), self.D.get('r1')
        t1 = self.D.get('b1_trace') or {}
        self.check('T3.1_bullet_hull', 'PASS' if h1 is not None and r1 is not None and abs((h1 - r1) - 3.0) < 0.05 else 'FAIL',
                   'TestBullet 25 m to port at the hull\'s side (1 m above the hull origin): ship %s -> %s (want -3); first Visibility hit on '
                   'the line %s (want ship 1\'s Mesh: a PA_Airship box; the hull\'s collision ignores Visibility since the helm / deck change, '
                   'component %s)' % (h1, r1, t1, t1.get('comp')), {'first_hit': t1})
        if self.D.get('b2_none'):
            self.check('T3.2_bullet_turret', 'FAIL', 'no living turret on ship 1')
        else:
            a, b = self.D.get('h2') or (None, None), self.D.get('r2') or (None, None)
            ok = a[0] is not None and b[0] is not None and abs((a[0] - b[0]) - 3.0) < 0.05 and a[1] is not None and b[1] is not None and abs(a[1] - b[1]) < 0.01
            first = (self.D.get('b2_trace') or {}).get('actor')
            self.check('T3.2_bullet_turret', 'PASS' if ok else 'FAIL', 'TestBullet from 25 m outboard at the HitBox: turret '
                       '%s -> %s (want -3), ship %s -> %s (want unchanged); first Visibility hit on the line %s (%s: the redirect %s)' % (
                           a[0], b[0], a[1], b[1], self.D.get('b2_trace'), first,
                           'was needed' if first == self.ship.get_name() else 'was not needed (the line reached the turret directly)'))
        h3, r3 = self.D.get('h3'), self.D.get('r3')
        self.check('T3.3_bullet_character', 'PASS' if h3 is not None and r3 is not None and abs((h3 - r3) - 3.0) < 0.05 else 'FAIL',
                   'TestBullet at the on-foot player: %s -> %s (want -3 through the Pawn sweep, as before)' % (h3, r3))

    # ---- T2.6: the player shoots a ball down (GA_GunShoot), no splash
    def start_t2_gun(self):
        # The player rides ship 1's deck and shoots ship 2's ball hovering 1 m outside ship 1's port side (ship 1's hull is
        # the dummy 1 m away). From the start platform under the ship (run 1) the aim was ~50 deg up: the on-foot camera
        # boom then sits in the platform (the camera ray starts inside it) and 4 s of rounds missed the ball.
        self.teleport(self.ship, SPAWN, 0.0)
        o, e = self.ship.get_actor_bounds(False)
        ymin = o.y - e.y
        sl = v3(self.ship.get_actor_location())
        loc, traced = self.deck_point(self.ship, -400.0, 350.0)
        self.tp_char(loc, -90.0)
        edge, _ = self.deck_point(self.ship, -600.0, ymin - sl[1] + 100.0)
        self.D['B0'] = [sl[0] - 600.0, ymin - 100.0 - 50.0, max(loc[2], edge[2]) + 150.0]
        self.D['ball'] = self.spawn_ball(self.D['B0'], (200.0, 0.0, 0.0), self.ship2, 60.0, 0.0)
        self.D['hp'] = []
        self.D['n'] = 0
        self.line('INFO', 'player on ship 1\'s deck at %s (hull trace %s), ball at %s (%.0f cm away)' % (r(loc, 0), traced, r(self.D['B0'], 0),
                                                                                                    dist(loc, self.D['B0'])))

    def ph_t2_gun(self, el):
        # 1 s after the shoot-down: the health of ship 1, the player and ship 2 again (no splash); the shot-down ball is
        # removed 1 s after it went down, so this doesn't wait for it to exist
        if 'down_t' in self.D:
            if el >= self.D['down_t'] + 1.0 and 'h_after' not in self.D:
                self.D['h_after'] = (self.tele(self.ship).get('Health'), self.health(self.char), self.tele(self.ship2).get('Health'))
                self.D['phase_done'] = True
            return
        b = self.D.get('ball')
        if not valid(b):
            return
        st = self.ball_state(b)
        if not self.D['hp'] or self.D['hp'][-1][1] != st.get('health') or self.D['hp'][-1][2] != st.get('shot_down'):
            self.D['hp'].append((r(el, 3), st.get('health'), st.get('shot_down')))
        if st.get('shot_down'):
            self.D['down_t'] = el
            self.D['h_at_down'] = (self.tele(self.ship).get('Health'), self.health(self.char), self.tele(self.ship2).get('Health'))
            return
        verr = self.aim_at(v3(b.get_actor_location()), lag_comp=True)
        # Fire held until the ball is down (30 hits at ~4.5 rounds/s) or 15 s
        if 0.6 <= el < 15.0:
            self.inject('IA_LMB')
            self.D['n'] += 1
        if int(el * 4) != self.D.get('_k'):
            # what the crosshair meets (first Visibility hit, nothing ignored / the shooter ignored) and the gun's burst
            # cues alive (one per round): tells a miss from no round at all
            self.D['_k'] = int(el * 4)
            _, _, a0, _ = self.cam_ray()
            _, _, a1, _ = self.cam_ray(ignore=[self.char])
            try:
                cues = len(unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, GC_GUN_BURST)))
            except Exception:  # noqa: BLE001
                cues = None
            self.D.setdefault('diag', []).append((r(el, 2), a0.get_name() if a0 else None, a1.get_name() if a1 else None, cues, st.get('health'), verr))
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
                   {'health_track': hp, 'diag (el, crosshair first hit, shooter ignored, burst cues, ball health, view error yaw/pitch)': self.D.get('diag')})

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

    # ---- T2.8 (S, review 2026-11-27): the ship's own ball does not hurt its own crew or itself. One player, so one role at a
    # time, each inside the 6 m splash of a ball of ship 1 that bursts on the port wall 1 m off L1's muzzle (2.5 m and 1.5 m
    # in the first runs). 'Inside the splash' is what the ball's own query says (in_splash: the same overlap from Python),
    # not the distance to the character's centre the first version asked for (< 600): L1's seat is 5 m inboard of its
    # muzzle, the gunner's centre was 6.07-6.44 m from the burst and his capsule inside the query all the same: a deck
    # rider beside the gun (a test ball of ship 1 from the muzzle), the gunner of L1 (its own shot, Aura.Airship.
    # StationFire), then the pilot aboard (a real port broadside, IA_AirshipFire, Classic). The pilot stands more than 6 m
    # from every point outside the hull, so his case is the hull's: a burst within the radius of the hull's collision would
    # cost a ship that is not the source 0.3 x the ball's damage (the falloff is clamped past the radius; the overlap decides)
    # and its pilot the crew's share of that. T2.5 is the control: the same splash takes 21 health from a player who is not
    # crew at 5.5 m.
    def start_t2_own(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        l1 = self.geo['L1']
        self.teleport(self.ship, (SPAWN[0], PORT_FACE_Y + 100.0 - l1[1], SPAWN[2]), 0.0)

    def in_splash(self, p, radius=600.0):
        """names of the actors the cannonball's own splash query finds at p (AAirshipCannonball: an overlap of Pawn /
        PhysicsBody / WorldDynamic bodies with a sphere of SplashRadius; whoever is in it is hurt unless it is the source
        ship or its crew, the falloff clamped at the radius). The same query from Python: 'inside the splash' is this,
        not the distance to an actor's centre (a capsule 34 cm wide is in it up to 6.3 m from its centre)."""
        try:
            q = unreal.ObjectTypeQuery
            res = unreal.SystemLibrary.sphere_overlap_actors(self.w, unreal.Vector(*p), float(radius),
                                                             [q.OBJECT_TYPE_QUERY2, q.OBJECT_TYPE_QUERY3, q.OBJECT_TYPE_QUERY4], None, [])
            return sorted(set(a.get_name() for a in (res or []) if a is not None))
        except Exception:  # noqa: BLE001
            self.err('in_splash')
            return None

    def own_case(self, t0):
        bs = [b for _, b in self.balls_since(t0, 't2_own')]
        imp = self.impact_of(bs[0]) if bs else None
        ca = v3(self.char.get_actor_location())
        d = dist(imp, ca) if imp else None
        hit = self.in_splash(imp) if imp else None
        return {'balls': len(bs), 'impact': r(imp, 0) if imp else None, 'd_cm': r(d, 0) if d is not None else None,
                'in_splash': {'player': bool(hit) and self.char.get_name() in hit, 'ship': bool(hit) and self.ship.get_name() in hit},
                'damage': bs[0].get('damage') if bs else None, 'health': self.health(self.char), 'ship_health': self.tele(self.ship).get('Health'),
                'info': self.char_info(self.char, self.ship)}

    def ph_t2_own(self, el):
        D, s = self.D, self.ship
        l1 = self.geo['L1']
        mz = self.world_of(s, l1)
        if el >= 0.4 and 'tp' not in D:
            D['tp'] = True
            loc, traced = self.deck_point(s, l1[0] + 150.0, l1[1] + 185.0)
            D['rider_traced'] = traced
            self.tp_char(loc, -90.0)
        if el >= 1.4 and 'b1' not in D:
            D['b1'] = self.now
            D['h0'] = (self.health(self.char), self.tele(s).get('Health'))
            D['rider0'] = self.char_info(self.char, s)
            self.spawn_ball(mz, (0.0, -7000.0, 0.0), s, 60.0, 0.0)
        if 'b1' in D and 'r1' not in D and self.now >= D['b1'] + 0.8:
            D['r1'] = self.own_case(D['b1'])
        if el >= 2.6 and 'm' not in D:
            D['m'] = True
            self.cmd('Aura.Airship.Mount 0 0')
        if el >= 4.0 and 'b2' not in D and 'm' in D:
            D['b2'] = self.now
            D['h2'] = (self.health(self.char), self.tele(s).get('Health'))
            D['gunner'] = same(self.gunner(s, 0), self.char)
            self.cmd('Aura.Airship.StationFire 0 %.0f %.0f %.0f' % (mz[0], PORT_FACE_Y, mz[2]))
        if 'b2' in D and 'r2' not in D and self.now >= D['b2'] + 1.0:
            D['r2'] = self.own_case(D['b2'])
            self.cmd('Aura.Airship.Dismount 0')
        # the pilot aboard: a real port broadside (the camera's side, Classic so that no scheme logic turns the hull)
        if 'r2' in D and 'p_board' not in D and self.now >= D['b2'] + 1.7:
            D['p_board'] = self.now
            self.set_scheme(s, self.cfg['aim_scheme'])
            self.cmd('Aura.Airship.Board 0')
        if 'p_board' in D and 'fire_t' not in D:
            self.aim_at([mz[0], PORT_FACE_Y, mz[2]])
            if self.now >= D['p_board'] + 2.0:
                D['h3'] = (self.health(self.char), self.tele(s).get('Health'))
                D['piloting'] = same(self.pawn(), s) and same(s.get_pilot(), self.char)
                D['mz3'] = [self.world_of(s, self.geo[c]) for c in ('L1', 'L2')]      # at the shot: the recoil moves the ship
                self.fire_side('port')
        elif 'fire_t' in D and 'r3' not in D:
            self.fire_fallback()
            if self.now >= D['fire_t'] + 1.2:
                bs = [b for _, b in self.balls_since(D['fire_t'], 't2_own')]
                mzs = D['mz3']
                imps = [self.impact_of(b) for b in bs]
                hits = [self.in_splash(i) if i else None for i in imps]
                D['r3'] = {'balls': len(bs), 'impacts': [r(i, 0) if i else None for i in imps],
                           'ship_in_splash': [bool(h) and s.get_name() in h for h in hits],
                           'from_own_muzzle_cm': [r(min(dist(i, m) for m in mzs), 0) if i else None for i in imps],
                           'damage': [b.get('damage') for b in bs], 'health': self.health(self.char),
                           'ship_health': self.tele(s).get('Health'), 'fallback': bool(D.get('fb'))}
                self.cmd('Aura.Airship.Exit 0')
        if 'r3' in D and self.now >= D['fire_t'] + 1.8:
            D['phase_done'] = True

    def end_t2_own(self):
        D = self.D
        h0, h2, r1, r2 = D.get('h0') or (None, None), D.get('h2') or (None, None), D.get('r1') or {}, D.get('r2') or {}

        def good(h, q):
            return (q.get('balls', 0) >= 1 and bool((q.get('in_splash') or {}).get('player')) and h[0] is not None and q.get('health') == h[0]
                    and h[1] is not None and q.get('ship_health') == h[1])

        def would(q):
            return r((q.get('damage') or 60.0) * (1.0 - 0.7 * min(1.0, q['d_cm'] / 600.0)), 1) if q.get('d_cm') is not None else None
        h3, r3 = D.get('h3') or (None, None), D.get('r3') or {}
        near = [x for x in (r3.get('ship_in_splash') or []) if x]
        ok3 = (bool(D.get('piloting')) and len(near) >= 1 and h3[0] is not None and r3.get('health') == h3[0] and h3[1] is not None
               and r3.get('ship_health') == h3[1])
        ok = good(h0, r1) and good(h2, r2) and bool(D.get('gunner')) and bool((D.get('rider0') or {}).get('rider')) and ok3
        self.check('T2.8_own_crew_splash_S', 'PASS' if ok else 'FAIL', 'ship 1 with L1\'s muzzle 1 m from the port wall. Deck rider beside L1 (passenger '
                   '%s, deck traced %s): a ball of ship 1 from the muzzle bursts on the wall %s cm from the rider\'s centre; the ball\'s own splash '
                   'query there (a 6 m overlap, repeated from Python) holds the rider and the ship: %s (want the rider in it; a player who is '
                   'not crew would lose %s there, T2.5): rider health %s -> %s, ship %s -> %s (want unchanged). Gunner of L1 (%s), its own shot '
                   '(StationFire): bursts %s cm from the gunner\'s centre, the query holds %s (want the gunner in it; not crew, a 60 ball: -%s): '
                   'gunner %s -> %s, ship %s -> %s (want unchanged). Pilot aboard (%s), a real port broadside (IA_AirshipFire%s): %s balls burst '
                   '%s cm from the muzzles they left, the query holds the ship: %s (want >= 1 True; a ship that is not the source would lose '
                   '0.3 x the ball\'s damage there and its pilot the crew\'s share): pilot %s -> %s, ship %s -> %s (want unchanged)' % (
                       (D.get('rider0') or {}).get('rider'), D.get('rider_traced'), r1.get('d_cm'), r1.get('in_splash'), would(r1), h0[0],
                       r1.get('health'), h0[1], r1.get('ship_health'), D.get('gunner'), r2.get('d_cm'), r2.get('in_splash'), would(r2), h2[0],
                       r2.get('health'), h2[1], r2.get('ship_health'), D.get('piloting'), ', FALLBACK RequestFire' if r3.get('fallback') else '',
                       r3.get('balls'), r3.get('from_own_muzzle_cm'), r3.get('ship_in_splash'), h3[0], r3.get('health'), h3[1],
                       r3.get('ship_health')),
                   {'rider': r1, 'gunner': r2, 'pilot': r3, 'h0': h0, 'h2': h2, 'h3': h3})
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.set_scheme(self.ship, self.cfg['scheme'])
        if self.gunner(self.ship, 0) is not None:
            self.cmd('Aura.Airship.Dismount 0')
        self.tp_char(CHAR_FOOT, 0.0)
        self.teleport(self.ship, SPAWN, 0.0)

    # ---- T8.1 (S): F under the hull does nothing (Talal 11-25: "if below hull, only be able to drive once close enough to
    # grab the steering wheel"; D8's BoardBelowDistance is 0 = off by default, the code path stays for a harness that sets it)
    def gap_up(self, ship, loc, reach=3000.0):
        """cm from loc straight up to the hull's collision (the old board-from-below test's own trace), or None."""
        try:
            res = self.hull(ship).line_trace_component(unreal.Vector(*loc), unreal.Vector(loc[0], loc[1], loc[2] + reach), False, False, False)
            if isinstance(res, tuple) and not (isinstance(res[0], bool) and not res[0]):
                p = next((v3(x) for x in res if isinstance(x, unreal.Vector)), None)
                return r(p[2] - loc[2], 1) if p else None
        except Exception:  # noqa: BLE001
            self.err('gap_up')
        return None

    def start_t8_below(self):
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['cases'] = []

    def t8_case(self, el, t0, want_gap, key):
        """t0: put the player on the ground under the hull's centre; t0 + 0.4: move the ship so the gap is want_gap; t0 + 0.6:
        F (IA_AirshipBoard); t0 + 1.2: boarded or not; then back on foot (Exit) if it boarded."""
        if el >= t0 and key + 'g' not in self.D:
            self.D[key + 'g'] = True
            com = v3(self.hull(self.ship).get_center_of_mass())
            # the player itself is ignored too: since T8.1 was turned around (nobody boards in the first case) the player still
            # stands under the hull centre for the second case; the trace hit its head, the player was put 1.4 m up in the
            # air and the ship was placed while it fell (first run 2026-11-27: the 12 m case measured 1265.7 cm)
            own = [self.char]
            try:
                own += list(self.char.get_attached_actors())
            except Exception:  # noqa: BLE001
                self.err('attached_actors')
            tr = self.trace(com, [com[0], com[1], com[2] - 5000.0], [self.ship] + self.turrets(self.ship) + own)
            if not tr or not tr.get('at'):
                self.D[key] = {'error': 'no ground under the hull centre: %s' % tr}
                return
            caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
            hh = caps.get_scaled_capsule_half_height() if caps else 90.0
            self.D[key + 'foot'] = [tr['at'][0], tr['at'][1], tr['at'][2] + hh + 2.0]
            self.tp_char(self.D[key + 'foot'], 0.0)
        if el >= t0 + 0.4 and key + 'm' not in self.D and key + 'foot' in self.D:
            self.D[key + 'm'] = True
            loc = v3(self.char.get_actor_location())
            g0 = self.gap_up(self.ship, loc)
            if g0 is not None:
                sl = v3(self.ship.get_actor_location())
                self.teleport(self.ship, (sl[0], sl[1], sl[2] + (want_gap - g0)), self.ship.get_actor_rotation().yaw)
        if el >= t0 + 0.6 and key + 'f' not in self.D and key + 'm' in self.D:
            self.D[key + 'f'] = True
            loc = v3(self.char.get_actor_location())
            self.D[key + 'gap'] = self.gap_up(self.ship, loc)
            self.D[key + 'seat'] = None
            try:
                self.D[key + 'seat'] = r(dist(loc, v3(self.ship.get_pilot_seat_location())), 0)
            except Exception:  # noqa: BLE001
                pass
            self.inject('IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (%s)' % key)
        if el >= t0 + 1.2 and key not in self.D and key + 'f' in self.D:
            self.D[key] = {'gap_cm': self.D.get(key + 'gap'), 'seat_cm': self.D.get(key + 'seat'), 'boarded': same(self.pawn(), self.ship),
                           'pilot': self.ship.get_pilot().get_name() if self.ship.get_pilot() else None}
            if self.D[key]['boarded']:
                self.cmd('Aura.Airship.Exit 0')

    def ph_t8_below(self, el):
        self.t8_case(el, 0.3, 700.0, 'b7')
        self.t8_case(el, 2.8, 1200.0, 'b12')

    def end_t8_below(self):
        b7, b12 = self.D.get('b7') or {}, self.D.get('b12') or {}
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        below = None
        try:
            below = float(self.settings().get_editor_property('BoardBelowDistance'))
        except Exception:  # noqa: BLE001
            self.err('board_below_setting')
        ok = b7.get('boarded') is False and b12.get('boarded') is False and b7.get('gap_cm') is not None and abs(b7['gap_cm'] - 700.0) < 50.0 \
            and b12.get('gap_cm') is not None and abs(b12['gap_cm'] - 1200.0) < 50.0
        self.check('T8.1_no_board_below_S', 'PASS' if ok else 'FAIL', 'the player on the ground under the hull\'s centre, F (IA_AirshipBoard): %s cm below '
                   'the belly (straight up to the hull collision; %s cm from the helm seat) -> boarded %s (want False); %s cm below (%s cm from the '
                   'seat) -> boarded %s (want False); UAirshipSettings.BoardBelowDistance %s (0 = off: the helm is taken only at the wheel, '
                   'T8.2 / T8.3)' % (b7.get('gap_cm'), b7.get('seat_cm'), b7.get('boarded'), b12.get('gap_cm'), b12.get('seat_cm'),
                                     b12.get('boarded'), below), {'b7': b7, 'b12': b12, 'BoardBelowDistance': below})
        self.teleport(self.ship, SPAWN, 0.0)

    # ---- T8.2 / T8.3 / T8.4 / T8.6 (S), Talal 11-25 (SPEC_A.md 6.8): "the player should only be able to drive mount the
    # ship when close enough to hold steering wheel" and "when player exits, the character should keep its position in
    # front of the steering wheel, as when driving". F is the real key path (IA_AirshipBoard -> ServerRequestBoard ->
    # TryUseNearest -> AAirshipPawn::IsWithinHelmReach; IA_AirshipExit -> UnboardPilot); the console Board still seats a
    # player from anywhere (the other phases use it).
    def helm_geo(self):
        """(seat, wheel hub) in hull space: the PilotSeat point (the feet) and the Helm_Wheel bone"""
        seat = self.rel(self.ship, v3(self.ship.get_pilot_seat_location()))
        try:
            wheel = self.local_socket(self.ship, 'Helm_Wheel')
        except Exception:  # noqa: BLE001
            self.err('helm_wheel_socket')
            wheel = [seat[0] + 55.0, seat[1], seat[2] + 96.0]
        return seat, wheel

    def char_rel(self):
        return self.rel(self.ship, v3(self.char.get_actor_location()))

    def char_base(self):
        """name of the actor the character's movement base belongs to (None: no base)"""
        try:
            a = unreal.Pawn.get_movement_base_actor(self.char)       # APawn::GetMovementBaseActor (static, BlueprintPure)
            return a.get_name() if a is not None else None
        except Exception:  # noqa: BLE001
            self.err('char_base')
            return None

    def trace_who(self, a, b, ignore=None):
        """self.trace plus 'is_char': the first hit is the player's character or an actor attached to it"""
        d = None
        try:
            res = unreal.SystemLibrary.line_trace_single(self.w, unreal.Vector(*a), unreal.Vector(*b), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, ignore or [], unreal.DrawDebugTrace.NONE, True)
            ok, imp, act, comp = hit_info(res)
            par = act.get_attach_parent_actor() if act is not None else None
            d = {'hit': ok, 'at': r(imp, 1) if imp else None, 'actor': act.get_name() if act else None, 'comp': comp.get_name() if comp else None,
                 'is_char': bool(same(act, self.char) or same(par, self.char)), 'is_ship': bool(same(act, self.ship))}
        except Exception:  # noqa: BLE001
            self.err('trace_who')
        return d

    def feet_over_deck(self, rel):
        """(cm of the capsule's bottom over the deck surface under it, that surface's hull-space z); the deck = deck_comp,
        traced from 60 cm above the feet to 2 m below them (so a box over the head doesn't count)"""
        feet = rel[2] - self.char_hh()
        hit = self.deck_hit(self.ship, rel[0], rel[1], feet + 60.0, feet - 200.0)
        if hit is None:
            return None, None
        top = self.rel(self.ship, hit)[2]
        return r(feet - top, 1), r(top, 1)

    def start_t8_helm(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['trk'] = []
        try:
            st = self.settings()
            self.D['cfg'] = dict((n, r(float(st.get_editor_property(n)), 1)) for n in (
                'HelmReach', 'HelmReachHeight', 'BoardDistance', 'BoardHullDistance', 'BoardBelowDistance'))
        except Exception:  # noqa: BLE001
            self.err('helm_settings')

    def ph_t8_helm(self, el):
        yaw = self.ship.get_actor_rotation().yaw
        if el >= 0.3 and 'geo' not in self.D:
            seat, wheel = self.helm_geo()
            self.D['geo'] = {'seat': r(seat, 1), 'wheel': r(wheel, 1), 'deck_is_pa': None}
            try:
                self.D['geo']['deck_is_pa'] = bool(call(self.ship, 'is_deck_on_physics_asset'))
            except Exception:  # noqa: BLE001
                self.err('is_deck_on_physics_asset')
            # 2.5 m behind the wheel on the centre line: on the planks, 1.95 m from the standing spot (HelmReach 150)
            loc, traced = self.deck_point(self.ship, wheel[0] - 250.0, wheel[1])
            self.D['far_traced'] = traced
            self.tp_char(loc, yaw)
        geo = self.D.get('geo')
        if geo is None:
            return
        seat, wheel = geo['seat'], geo['wheel']
        if el >= 1.3 and 'far_f' not in self.D:
            self.D['far_f'] = True
            rel = self.char_rel()
            self.D['far'] = {'rel': r(rel, 1), 'wheel_h_cm': r(math.hypot(rel[0] - wheel[0], rel[1] - wheel[1]), 1),
                             'seat_h_cm': r(math.hypot(rel[0] - seat[0], rel[1] - seat[1]), 1), 'feet_over_deck': self.feet_over_deck(rel),
                             'info': self.char_info(self.char, self.ship), 'traced': self.D.get('far_traced')}
            self.inject('IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (2.5 m behind the wheel)')
        if el >= 2.1 and 'far_res' not in self.D and 'far_f' in self.D:
            self.D['far_res'] = {'boarded': same(self.pawn(), self.ship), 'pilot': self.ship.get_pilot().get_name() if self.ship.get_pilot() else None}
            if self.D['far_res']['boarded']:
                self.cmd('Aura.Airship.Exit 0')
        if el >= 2.4 and 'at_tp' not in self.D:
            self.D['at_tp'] = True
            loc, traced = self.deck_point(self.ship, seat[0], seat[1])
            self.D['at_traced'] = traced
            self.tp_char(loc, yaw)
        if el >= 3.4 and 'at_f' not in self.D:
            self.D['at_f'] = True
            rel = self.char_rel()
            self.D['at'] = {'rel': r(rel, 1), 'wheel_h_cm': r(math.hypot(rel[0] - wheel[0], rel[1] - wheel[1]), 1),
                            'seat_h_cm': r(math.hypot(rel[0] - seat[0], rel[1] - seat[1]), 1), 'feet_over_deck': self.feet_over_deck(rel),
                            'info': self.char_info(self.char, self.ship), 'traced': self.D.get('at_traced')}
            self.inject('IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (at the wheel)')
        if el >= 4.2 and 'at_res' not in self.D and 'at_f' in self.D:
            par = self.char.get_attach_parent_actor()
            self.D['at_res'] = {'boarded': same(self.pawn(), self.ship), 'pilot_is_char': same(self.ship.get_pilot(), self.char),
                                'att': par.get_name() if par else None}
            # the driving pose: the character attached at the seat (feet + half height + PilotSeatClearance)
            self.D['drive'] = self.char_rel()
        if el >= 4.8 and 'exit_t' not in self.D and (self.D.get('at_res') or {}).get('boarded'):
            self.D['exit_t'] = el
            self.D['v_ship'] = r(v3(self.ship.get_velocity()), 1)
            self.inject('IA_AirshipExit')
            self.event('inject', what='IA_AirshipExit (pilot at the wheel)')
        if 'exit_t' in self.D:
            if 'foot_t' not in self.D and same(self.pawn(), self.char):
                self.D['foot_t'] = el
            if 'foot_t' in self.D and el <= self.D['foot_t'] + 1.6:
                rel = self.char_rel()
                self.D['trk'].append((r(el - self.D['foot_t'], 3), r(rel, 1), (self.char_info(self.char) or {}).get('mode')))
            if 'foot_t' in self.D and el >= self.D['foot_t'] + 0.6 and 'ex' not in self.D:
                rel = self.char_rel()
                self.D['ex'] = {'rel': r(rel, 1), 'info': self.char_info(self.char, self.ship), 'base': self.char_base(),
                                'feet_over_deck': self.feet_over_deck(rel), 'char_v': r(v3(self.char.get_velocity()), 1)}
            if 'foot_t' in self.D and el >= self.D['foot_t'] + 1.7 and 'tr' not in self.D:
                # T8.6: the player stands on the planks, inside the hull's UCX lid (3.5-5.8 m high there). Visibility lines
                # at it from 10 m above and from 25 m to port; then from above past the player: the deck box under it.
                c = v3(self.char.get_actor_location())
                up, rg = v3(self.ship.get_actor_up_vector()), v3(self.ship.get_actor_right_vector())
                feet = [c[i] - up[i] * (self.char_hh() + 40.0) for i in range(3)]
                above = [c[i] + up[i] * 1000.0 for i in range(3)]
                port = [c[i] - rg[i] * 2500.0 for i in range(3)]
                own = [self.char]
                try:
                    own += list(self.char.get_attached_actors())
                except Exception:  # noqa: BLE001
                    self.err('attached_actors')
                self.D['tr'] = {'above': self.trace_who(above, c), 'port': self.trace_who(port, c), 'above_past_player': self.trace_who(above, feet, own),
                                'char': self.char.get_name(), 'ship': self.ship.get_name()}
                self.D['phase_done'] = True

    def end_t8_helm(self):
        geo, cfg = self.D.get('geo') or {}, self.D.get('cfg')
        far, fr = self.D.get('far') or {}, self.D.get('far_res') or {}
        fi = far.get('info') or {}
        ok = fr.get('boarded') is False and fr.get('pilot') is None and far.get('wheel_h_cm') is not None and abs(far['wheel_h_cm'] - 250.0) <= 30.0 \
            and fi.get('mode') == 'MOVE_WALKING'
        self.check('T8.2_no_helm_2p5m_S', 'PASS' if ok else 'FAIL', 'the player on the planks %s cm behind the wheel (hull %s, %s cm from the '
                   'standing spot, feet %s cm over the deck box at hull z %s, %s), F (IA_AirshipBoard): boarded %s, pilot %s (want not boarded); '
                   'helm %s; settings %s' % (far.get('wheel_h_cm'), far.get('rel'), far.get('seat_h_cm'), (far.get('feet_over_deck') or [None])[0],
                                             (far.get('feet_over_deck') or [None, None])[1], fi.get('mode'), fr.get('boarded'), fr.get('pilot'), geo, cfg),
                   {'far': far, 'res': fr, 'geo': geo, 'settings': cfg})
        at, ar = self.D.get('at') or {}, self.D.get('at_res') or {}
        ok = ar.get('boarded') is True and ar.get('pilot_is_char') is True and ar.get('att') == self.ship.get_name()
        self.check('T8.3_helm_at_wheel_S', 'PASS' if ok else 'FAIL', 'the player on the planks at the wheel (hull %s, %s cm from the standing spot, '
                   '%s cm from the wheel hub, feet %s cm over the deck box, %s), F: %s (want boarded, the pilot, attached to the ship)' % (
                       at.get('rel'), at.get('seat_h_cm'), at.get('wheel_h_cm'), (at.get('feet_over_deck') or [None])[0],
                       (at.get('info') or {}).get('mode'), ar), {'at': at, 'res': ar})
        ex, drive, trk = self.D.get('ex') or {}, self.D.get('drive'), self.D.get('trk') or []
        ei = ex.get('info') or {}
        dxy = d3 = dz = None
        if ex.get('rel') and drive:
            dxy = math.hypot(ex['rel'][0] - drive[0], ex['rel'][1] - drive[1])
            d3 = dist(ex['rel'], drive)
            dz = ex['rel'][2] - drive[2]
        fod = (ex.get('feet_over_deck') or [None, None])
        late = [x[1] for x in trk if x[0] >= 0.6]
        span = max(dist(p, late[0]) for p in late) if late else None
        first = trk[0][1] if trk else None
        jump0 = math.hypot(first[0] - drive[0], first[1] - drive[1]) if first and drive else None
        modes = sorted(set(x[2] for x in trk if x[2]))
        ok = ('foot_t' in self.D and dxy is not None and dxy <= 10.0 and ei.get('att') is None and ei.get('mode') == 'MOVE_WALKING'
              and ei.get('rider') is True and ex.get('base') == self.ship.get_name() and fod[0] is not None and abs(fod[0]) <= 5.0
              and span is not None and span <= 5.0 and jump0 is not None and jump0 <= 10.0 and 'MOVE_FALLING' not in modes)
        self.check('T8.4_exit_in_place_S', 'PASS' if ok else 'FAIL', 'pilot F (IA_AirshipExit) at rest (ship %s cm/s): on foot %s s after F; driving '
                   'pose (hull) %s, 0.6 s after the exit %s: %s cm apart in the hull\'s xy (want <= 10; first frame on foot %s cm), %s cm in z '
                   '(the seat\'s clearance down onto the deck box; 3D %s cm); %s, attached to %s, base %s (want walking, detached, the ship), '
                   'rider %s, capsule %s; feet %s cm over the deck box at hull z %s (want within 5: on the planks\' boxes); modes after the exit '
                   '%s (want no falling: no launch); moved %s cm over the next second (want <= 5); character velocity %s' % (
                       self.D.get('v_ship'), r(self.D['foot_t'] - self.D['exit_t'], 2) if 'foot_t' in self.D and 'exit_t' in self.D else None,
                       r(drive, 1) if drive else None, ex.get('rel'), r(dxy, 1) if dxy is not None else None,
                       r(jump0, 1) if jump0 is not None else None, r(dz, 1) if dz is not None else None, r(d3, 1) if d3 is not None else None,
                       ei.get('mode'), ei.get('att'), ex.get('base'), ei.get('rider'), ei.get('coll'), fod[0], fod[1], modes,
                       r(span, 1) if span is not None else None, ex.get('char_v')),
                   {'drive': drive, 'exit': ex, 'track': trk[::3], 'xy_cm': dxy, 'z_cm': dz})
        tr = self.D.get('tr') or {}
        a, pt, past = tr.get('above') or {}, tr.get('port') or {}, tr.get('above_past_player') or {}
        ok = bool(a.get('is_char')) and bool(pt.get('is_char')) and bool(past.get('is_ship')) and past.get('comp') == 'Mesh'
        self.check('T8.6_deck_player_hit_by_trace_S', 'PASS' if ok and tr else 'FAIL', 'the player on the planks at the wheel (inside the hull\'s UCX lid): '
                   'first Visibility hit from 10 m above %s, from 25 m to port %s (want the player %s on both: the hull\'s collision ignores '
                   'Visibility); from above past the player %s (want ship 1\'s Mesh: the deck box of PA_Airship)' % (a, pt, tr.get('char'), past), tr)

    # ---- t8_reach (opt-in: AS59_ONLY="t8_reach"; INFO only, 2026-11-27): what a player on foot reaches on the parked ship.
    # Jump and jump + air jump heights on the main deck; F under the port turret's seat from the main deck, standing and
    # near the top of a jump (AAirshipPawn::IsWithinStationRange: within StationMountDistance horizontally, the capsule
    # centre StationMountHeightBelow under .. StationMountHeightAbove over the seat, hull space).
    def start_t8_reach(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['z'] = []

    def ph_t8_reach(self, el):
        yaw = self.ship.get_actor_rotation().yaw
        if el >= 0.6 and 'tp1' not in self.D:
            self.D['tp1'] = True
            loc, _ = self.deck_point(self.ship, 300.0, 0.0)
            self.tp_char(loc, yaw)
        if el >= 1.6 and 'j1' not in self.D:
            self.D['j1'] = el
            self.D['z0'] = self.char_rel()[2]
            self.char.jump()
        if 'j1' in self.D and el >= self.D['j1'] + 0.1 and 'j1s' not in self.D:
            self.D['j1s'] = True
            self.char.stop_jumping()
        if 'j1' in self.D and el < 3.4:
            self.D['z'].append((r(el - self.D['j1'], 3), self.char_rel()[2] - self.D['z0'], (self.char_info(self.char) or {}).get('mode')))
        if el >= 3.4 and 'j2' not in self.D:
            self.D['j2'] = el
            self.D['zz'] = []
            self.D['z0b'] = self.char_rel()[2]
            self.char.jump()
        if 'j2' in self.D and el >= self.D['j2'] + 0.1 and 'j2s' not in self.D:
            self.D['j2s'] = True
            self.char.stop_jumping()
        # the air jump at the top of the first one: the air jump sets the upward speed to JumpZVelocity, it does not add to it
        if 'j2' in self.D and 'aj' not in self.D and el >= self.D['j2'] + 0.2 and float(self.char.get_velocity().z) <= 10.0:
            self.D['aj'] = el
            self.char.jump()
        if 'aj' in self.D and el >= self.D['aj'] + 0.1 and 'ajs' not in self.D:
            self.D['ajs'] = True
            self.char.stop_jumping()
        if 'j2' in self.D and el < 6.2:
            self.D['zz'].append((r(el - self.D['j2'], 3), self.char_rel()[2] - self.D['z0b'], (self.char_info(self.char) or {}).get('mode')))
        # F under the port turret's seat (station 4): standing on the main deck, then near the top of a jump
        if el >= 6.2 and 'tp2' not in self.D:
            self.D['tp2'] = True
            seat = self.rel(self.ship, v3(self.ship.get_station_seat_location(4)))
            self.D['seat'] = r(seat, 1)
            # the main deck under the forward deck: at x 1900 its planks are 195 cm to each side (the forward deck overhangs
            # the hull at the turrets), so 150 cm off the centre line: 1.4 m from the seat's spot in the hull's xy
            hit = self.deck_hit(self.ship, seat[0] - 100.0, math.copysign(150.0, seat[1]), 500.0, -200.0)
            self.D['under'] = r(self.rel(self.ship, hit), 1) if hit else None
            if hit:
                self.tp_char([hit[0], hit[1], hit[2] + self.char_hh() + 5.0], yaw)
        if el >= 7.2 and 'f1' not in self.D and self.D.get('under'):
            self.D['f1'] = {'rel': r(self.char_rel(), 1), 'mode': (self.char_info(self.char) or {}).get('mode')}
            self.inject('IA_AirshipBoard')
        if el >= 7.8 and 'r1' not in self.D and 'f1' in self.D:
            self.D['r1'] = {'gunner': same(self.gunner(self.ship, 4), self.char), 'boarded': same(self.pawn(), self.ship)}
            if self.D['r1']['gunner']:
                self.cmd('Aura.Airship.Dismount 0')
        if el >= 8.4 and 'j3' not in self.D and 'r1' in self.D and not self.D['r1']['gunner']:
            self.D['j3'] = el
            self.D['z0c'] = self.char_rel()[2]
            self.char.jump()
        if 'j3' in self.D and el >= self.D['j3'] + 0.1 and 'j3s' not in self.D:
            self.D['j3s'] = True
            self.char.stop_jumping()
        if 'j3' in self.D and 'f2' not in self.D and el >= self.D['j3'] + 0.2 and float(self.char.get_velocity().z) <= 60.0:
            self.D['f2'] = {'rel': r(self.char_rel(), 1), 'rise': r(self.char_rel()[2] - self.D['z0c'], 1), 't': r(el - self.D['j3'], 2),
                            'mode': (self.char_info(self.char) or {}).get('mode')}
            self.inject('IA_AirshipBoard')
        if 'f2' in self.D and 'r2' not in self.D and el >= self.D['j3'] + 1.0:
            par = self.char.get_attach_parent_actor()
            self.D['r2'] = {'gunner': same(self.gunner(self.ship, 4), self.char), 'rel': r(self.char_rel(), 1),
                            'att': par.get_name() if par else None}
            if self.D['r2']['gunner']:
                self.capture('t8_reach_turret', 'turret0', self.ship)
                self.cmd('Aura.Airship.Dismount 0')
        if 'r2' in self.D and 'r3' not in self.D and el >= self.D['j3'] + 2.2:
            rel = self.char_rel()
            fod = self.feet_over_deck(rel)
            if fod[0] is None:
                fod = self.feet_over_deck([rel[0] - 20.0, rel[1], rel[2]])
            self.D['r3'] = {'rel': r(rel, 1), 'info': self.char_info(self.char, self.ship), 'feet_over_deck': fod}
            self.D['phase_done'] = True

    def end_t8_reach(self):
        z1 = [x for x in self.D.get('z') or [] if x[2] == 'MOVE_FALLING']
        z2 = [x for x in self.D.get('zz') or [] if x[2] == 'MOVE_FALLING']
        a1, a2 = max((x[1] for x in z1), default=None), max((x[1] for x in z2), default=None)
        cm = gp(self.char, 'character_movement', 'CharacterMovement')
        jz, gs = float(cm.get_editor_property('jump_z_velocity')), float(cm.get_editor_property('gravity_scale'))
        self.check('T8.R1_jump_heights', 'INFO', 'on the main deck of the parked ship: a jump lifts the feet %s cm (in the air %s s), a jump + '
                   'the air jump at its top %s cm (air jump %s s after the jump; in the air %s s); JumpZVelocity %s, gravity scale %s -> '
                   '%s cm per jump' % (r(a1, 1) if a1 is not None else None, r(z1[-1][0] - z1[0][0], 2) if z1 else None,
                                       r(a2, 1) if a2 is not None else None,
                                       r(self.D['aj'] - self.D['j2'], 2) if 'aj' in self.D and 'j2' in self.D else None,
                                       r(z2[-1][0] - z2[0][0], 2) if z2 else None, jz, gs, r(jz * jz / (2.0 * 980.0 * gs), 1)),
                   {'jump': z1[::3], 'air_jump': z2[::3]})
        st = self.settings()
        cfg = dict((n, r(float(st.get_editor_property(n)), 1)) for n in ('StationMountDistance', 'StationMountHeightAbove', 'StationMountHeightBelow'))
        seat, f1, f2 = self.D.get('seat'), self.D.get('f1') or {}, self.D.get('f2') or {}
        d1 = r(f1['rel'][2] - seat[2], 1) if f1.get('rel') and seat else None
        d2 = r(f2['rel'][2] - seat[2], 1) if f2.get('rel') and seat else None
        self.check('T8.R2_turret_from_main_deck', 'INFO', 'port turret seat (hull) %s, the main deck under it %s; settings %s. Standing on the '
                   'main deck 1.4 m from the seat\'s spot in the hull\'s xy (hull %s, capsule centre %s cm from the seat in z), F: gunner %s. In a jump from '
                   'there, F %s s after the take-off (feet %s cm up, capsule centre %s cm from the seat in z, %s): %s; after Dismount: %s' % (
                       seat, self.D.get('under'), cfg, f1.get('rel'), d1, (self.D.get('r1') or {}).get('gunner'), f2.get('t'), f2.get('rise'), d2,
                       f2.get('mode'), self.D.get('r2'), self.D.get('r3')),
                   {'seat': seat, 'under': self.D.get('under'), 'f1': f1, 'r1': self.D.get('r1'), 'f2': f2, 'r2': self.D.get('r2'),
                    'r3': self.D.get('r3'), 'settings': cfg})
        self.tp_char(CHAR_FOOT, 0.0)

    # ---- T8.5 / T8.7 (S): a walker on the planks in flight. Its movement base is the Mesh's Hull body (kinematic, QueryOnly),
    # a child of the simulating hull: the CMC follows it after the physics step like the hull itself (IsSimulatedBase walks
    # up the attach parents), and a jump inherits the body's velocity (the kinematic target's, read back from the solver).
    def start_t8_walk(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.set_scheme(self.ship, self.cfg['aim_scheme'])
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['trk'] = []

    def fly_all(self, thr, steer):
        # the command flies EVERY ship of the world: ship 2 (parked) is cleared again in the same frame, as t9_input
        self.cmd('Aura.Airship.Input %s %s' % (thr, steer))
        try:
            if valid(self.ship2):
                self.ship2.debug_clear_input()
        except Exception:  # noqa: BLE001
            self.err('ship2_clear')

    def ph_t8_walk(self, el):
        if el >= 0.2 and 'tp' not in self.D:
            self.D['tp'] = True
            seat, _ = self.helm_geo()
            # 1.5 m behind the standing spot: open planks (the wheel 2 m ahead, the aft cannons 3 m to the sides)
            loc, traced = self.deck_point(self.ship, seat[0] - 150.0, seat[1])
            self.D['traced'] = traced
            self.tp_char(loc, self.ship.get_actor_rotation().yaw)
        if el >= 1.2 and 'go' not in self.D:
            self.D['go'] = True
            self.D['rel0'] = self.char_rel()
            self.fly_all(1, 0)
        if el >= 5.0 and 'turn' not in self.D:
            self.D['turn'] = True
            self.fly_all(1, 0.4)
        if el >= 8.0 and 'straight' not in self.D:
            self.D['straight'] = True
            self.fly_all(1, 0)
        if el >= 9.5 and 'jump' not in self.D:
            self.D['jump'] = el
            self.D['jump_rel'] = self.char_rel()
            self.D['jump_v'] = r(math.hypot(*(v3(self.ship.get_velocity())[:2])) / 100.0, 2)
            self.D['jump_info'] = self.char_info(self.char, self.ship)
            try:
                self.char.jump()
            except Exception:  # noqa: BLE001
                self.err('jump')
        if 'jump' in self.D and el >= self.D['jump'] + 0.15 and 'jump_stop' not in self.D:
            self.D['jump_stop'] = True
            try:
                self.char.stop_jumping()
            except Exception:  # noqa: BLE001
                self.err('stop_jumping')
        # T8.9: a second jump from the deck, then the air jump with the movement input held to starboard (the ship's right)
        cm = gp(self.char, 'character_movement', 'CharacterMovement')
        if el >= 12.4 and 'j2' not in self.D:
            self.D['j2'] = el
            self.D['j2_info'] = self.char_info(self.char, self.ship)
            try:
                self.char.jump()
            except Exception:  # noqa: BLE001
                self.err('jump2')
        if 'j2' in self.D and self.D['j2'] + 0.35 <= el <= self.D['j2'] + 1.1:
            try:
                self.char.add_movement_input(self.ship.get_actor_right_vector(), 1.0, False)
            except Exception:  # noqa: BLE001
                self.err('add_movement_input')
        if 'j2' in self.D and el >= self.D['j2'] + 0.5 and 'aj' not in self.D:
            self.D['aj'] = el
            try:
                self.char.stop_jumping()
                self.D['aj0'] = {'rel': self.char_rel(), 'mode': (self.char_info(self.char) or {}).get('mode'),
                                 'count': int(cm.get_editor_property('AirJumpCount')), 'v': r(v3(self.ship.get_velocity()), 0),
                                 'char_v': r(v3(self.char.get_velocity()), 0), 'max_walk': r(float(cm.get_editor_property('max_walk_speed')), 1)}
                self.char.jump()
            except Exception:  # noqa: BLE001
                self.err('air_jump')
        if 'aj' in self.D and el >= self.D['aj'] + 0.15 and 'aj_stop' not in self.D:
            self.D['aj_stop'] = True
            try:
                self.char.stop_jumping()
            except Exception:  # noqa: BLE001
                self.err('stop_jumping2')
        if 'aj' in self.D and el >= self.D['aj'] + 0.5 and 'aj1' not in self.D:
            try:
                self.D['aj1'] = {'rel': self.char_rel(), 'mode': (self.char_info(self.char) or {}).get('mode'),
                                 'count': int(cm.get_editor_property('AirJumpCount')), 'char_v': r(v3(self.char.get_velocity()), 0),
                                 'dt': r(el - self.D['aj'], 3)}
            except Exception:  # noqa: BLE001
                self.D['aj1'] = {}
                self.err('air_jump_read')
        if el >= 13.8 and 'clr' not in self.D:
            self.D['clr'] = True
            self.cmd('Aura.Airship.InputClear')
        if 'go' in self.D and int(el * 10) != self.D.get('_k'):
            self.D['_k'] = int(el * 10)
            rel = self.char_rel()
            ci = self.char_info(self.char, self.ship) or {}
            t = self.tele(self.ship)
            self.D['trk'].append({'el': r(el, 2), 'rel': r(rel, 1), 'mode': ci.get('mode'), 'rider': ci.get('rider'), 'base': self.char_base(),
                                  'fod': self.feet_over_deck(rel)[0], 'v': r(t.get('SpeedMS'), 2), 'roll': r(t.get('RollDeg'), 1),
                                  'yawrate': r(t.get('YawRateDegS'), 1)})

    def end_t8_walk(self):
        try:
            self.ship.debug_clear_input()
        except Exception:  # noqa: BLE001
            pass
        trk, rel0 = self.D.get('trk') or [], self.D.get('rel0')
        tj = self.D.get('jump')
        walk = [x for x in trk if tj is None or x['el'] < tj - 0.05]
        hh = self.char_hh()
        drift = max(math.hypot(x['rel'][0] - rel0[0], x['rel'][1] - rel0[1]) for x in walk) if walk and rel0 else None
        modes = sorted(set(x['mode'] for x in walk if x['mode']))
        riders = all(x['rider'] for x in walk) if walk else False
        bases = sorted(set(str(x['base']) for x in walk))
        fods = [x['fod'] for x in walk if x['fod'] is not None]
        vmax = max((x['v'] or 0.0) for x in walk) if walk else None
        roll = max(abs(x['roll'] or 0.0) for x in walk) if walk else None
        yr = max(abs(x['yawrate'] or 0.0) for x in walk) if walk else None
        # the capsule's bottom over the deck box, hull space: 2 cm standing level, up to ~10 on a banked deck (an upright capsule)
        # "carried": Classic at throttle 1 pulls 12 m/s^2 with the nose 16 deg down (as_43 d_throttle), 48 m/s after 5 s; as_45's
        # rider moved 22 cm at throttle 0.5 on the v1 deck. Within 1 m of its spot is carried (left behind = 400 m).
        ok = (walk and drift is not None and drift <= 100.0 and modes == ['MOVE_WALKING'] and riders and bases == [self.ship.get_name()]
              and len(fods) == len(walk) and min(fods) >= -6.0 and max(fods) <= 12.0 and vmax is not None and vmax >= 15.0)
        self.check('T8.5_walker_carried_S', 'PASS' if ok else 'FAIL', 'the player standing on the planks 1.5 m behind the helm (hull %s, deck traced %s), '
                   'Classic, throttle 1 for 8.3 s with a 3 s turn (steer 0.4): top %s m/s, roll up to %s deg, yaw rate up to %s deg/s; the player '
                   'moved at most %s cm in the hull\'s xy (want <= 100), modes %s (want walking), rider all the time %s, movement base %s (want '
                   'the ship), feet %s .. %s cm over the deck box (want -6 .. 12), %d samples' % (
                       r(rel0, 1) if rel0 else None, self.D.get('traced'), vmax, roll, yr, r(drift, 1) if drift is not None else None, modes, riders,
                       bases, min(fods) if fods else None, max(fods) if fods else None, len(walk)),
                   {'track': walk[::5]})
        tj2 = self.D.get('j2')       # T8.9's jumps come after T8.7 / T8.8's samples
        after = [x for x in trk if tj is not None and x['el'] >= tj and (tj2 is None or x['el'] < tj2 - 0.05)]
        air = [x for x in after if x['mode'] == 'MOVE_FALLING']
        land = None
        if air:
            land = next((x for x in after if x['el'] > air[-1]['el'] and x['mode'] == 'MOVE_WALKING'), None)
        jr = self.D.get('jump_rel')
        miss = math.hypot(land['rel'][0] - jr[0], land['rel'][1] - jr[1]) if land and jr else None
        top = max((x['rel'][2] for x in air), default=None)
        end = after[-1] if after else {}
        ok = (bool(air) and land is not None and miss is not None and miss <= 400.0 and end.get('mode') == 'MOVE_WALKING' and end.get('rider')
              and (self.D.get('jump_v') or 0.0) >= 15.0)
        self.check('T8.7_deck_jump_in_flight_S', 'PASS' if ok else 'FAIL', 'the player jumps (ACharacter::Jump) on the planks at %s m/s, throttle still 1: '
                   '%d samples in the air (hull z up to %s from %s), back on the deck (walking) at %s s after the jump, %s cm from the take-off '
                   'point in the hull\'s xy (want <= 400: the ship gains about a x t^2 / 2 on it; without the base\'s velocity it would be '
                   '%s m behind), end %s' % (self.D.get('jump_v'), len(air), top, jr[2] if jr else None,
                                            r(land['el'] - tj, 2) if land else None, r(miss, 0) if miss is not None else None,
                                            r((self.D.get('jump_v') or 0.0) * 1.2, 0), dict((k, end.get(k)) for k in ('rel', 'mode', 'rider', 'base'))),
                   {'jump': self.D.get('jump_info'), 'air': air, 'land': land})
        # T8.8 (added 2026-11-27 after the first deck run): the landing. The engine adds the base's velocity to the character
        # when it leaves the deck and never takes it off again on landing, so the walker landed 18 cm from its take-off point
        # and then slid ~1.5 m forward along the deck at 48 m/s until the wheel's box stopped it (T8.7's end pose was the
        # helm). Measured over the 1.5 s after the first walking sample, in the hull's xy.
        post = [x for x in after if land is not None and land['el'] <= x['el'] <= land['el'] + 1.5]
        slide = max((math.hypot(x['rel'][0] - land['rel'][0], x['rel'][1] - land['rel'][1]) for x in post), default=None)
        fwd = max((x['rel'][0] - land['rel'][0] for x in post), default=None)
        ok = land is not None and len(post) >= 10 and slide is not None and slide <= 50.0 and all(x['mode'] == 'MOVE_WALKING' for x in post)
        self.check('T8.8_deck_landing_no_slide_S', 'PASS' if ok else 'FAIL', 'after that landing (ship %s m/s): the walker moved at most %s cm '
                   'from the landing point in the hull\'s xy over the next 1.5 s (want <= 50: the ship\'s velocity it got at the take-off must '
                   'be taken off again on landing, else it slides along the deck at the ship\'s speed until the ground friction stops '
                   'it, 2.7 m at 48 m/s); furthest forward %s cm; %d samples, landing %s, 1.5 s later %s' % (
                       land.get('v') if land else None, r(slide, 1) if slide is not None else None, r(fwd, 1) if fwd is not None else None,
                       len(post), land.get('rel') if land else None, post[-1]['rel'] if post else None),
                   {'post': post})
        # T8.9 (added 2026-11-27): the air jump on a flying deck. UMyCharacterMovementComponent turns the horizontal velocity
        # toward the movement input on an air jump; in the air over the deck that velocity is the ship's 48 m/s plus the
        # player's own, and all of it was turned (read in the code, before any run): a direction key + the second jump threw
        # the player off the ship at the ship's speed. Only the part relative to the base the player left may turn.
        a0, a1 = self.D.get('aj0') or {}, self.D.get('aj1') or {}
        dx = dy = None
        if a0.get('rel') and a1.get('rel'):
            dx, dy = a1['rel'][0] - a0['rel'][0], a1['rel'][1] - a0['rel'][1]
        mw, dt = a0.get('max_walk'), a1.get('dt') or 0.5
        ok = (dx is not None and mw and a0.get('mode') == 'MOVE_FALLING' and a1.get('count') == (a0.get('count') or 0) + 1
              and abs(dx) <= 150.0 and 0.25 * mw * dt <= dy <= 2.0 * mw * dt + 100.0)
        self.check('T8.9_deck_air_jump_keeps_ship_speed_S', 'PASS' if ok else 'FAIL', 'a second jump from the planks, 0.5 s later the air jump '
                   '(ACharacter::Jump while %s) with the movement input to starboard, ship %s cm/s, player %s cm/s: air jumps %s -> %s (want '
                   '+1); %s s later the player is %s cm along the hull\'s x and %s cm to starboard of the air-jump point (want within 150 '
                   'cm along x: the ship\'s speed is kept; %s .. %s cm to starboard: MaxWalkSpeed %s cm/s relative to the ship; turning the '
                   'whole velocity leaves it %s m behind), player velocity then %s' % (
                       a0.get('mode'), a0.get('v'), a0.get('char_v'), a0.get('count'), a1.get('count'), dt, r(dx, 0) if dx is not None else None,
                       r(dy, 0) if dy is not None else None, r(0.25 * (mw or 0.0) * dt, 0), r(2.0 * (mw or 0.0) * dt + 100.0, 0), mw,
                       r(math.hypot(*(a0.get('v') or [0.0, 0.0])[:2]) * dt / 100.0, 0), a1.get('char_v')),
                   {'air_jump': a0, 'after': a1, 'start': self.D.get('j2_info')})
        # back for the drift phases: the walker to the start platform (the ship's teleport would leave it in the air)
        self.set_scheme(self.ship, self.cfg['scheme'])
        self.tp_char(CHAR_FOOT, 0.0)
        self.teleport(self.ship, SPAWN, 0.0)

    # ---- t8_boost (opt-in: AS59_ONLY="t8_boost"; INFO only; review 2026-11-27, must fix 2): what a player on foot reaches
    # with the game's own keys. F under the hull is gone (T8.1) and GA_GrappleSwing2 refuses the ship (its rope takes
    # WorldStatic / WorldDynamic only and never a pawn), so the ways up are the boost (GA_BoostBP: Shift on the ground,
    # W along the full control rotation while MOVE_Flying) and the jump (GA_JumpHover on Space: jump, air jump, hover).
    # First run: Shift on the ground starts GA_BoostBP but the character stays MOVE_Walking (a run at twice the walking
    # speed); the boost flies only while the character is MOVE_Flying, which is the hover (the third Space). GA_Boost's
    # CanActivateAbility refuses a falling character, not a hovering one.
    # Injected and nothing else: IA_Shift, IA_Move (W), IA_Space, the control rotation (the mouse), IA_AirshipBoard (F).
    #  T8.B1  from the ground 15 m to port of the helm: Shift + W on the ground for 2 s (what it does there), back to the
    #         spot, then Space, Space at the top, Space at the next top (hover), then Shift held with the view as the
    #         thrust direction and W as the thrust to a point outboard of the rail and on to 1.6 m over the planks behind
    #         the helm, keys let go, Space to drop out of the hover; W to the wheel; F. (Run 2 flew at the points with
    #         Shift + W held all the way: 26 m/s, past the ship and off the platform. Run 3 let the keys go early and
    #         waited: the character does not brake by itself in the air. Steering against the motion is what a player does.)
    #  T8.B2  on the open platform: W, Space (jump), Space at the top (air jump), Space at the next top (hover), until the
    #         feet are back on the ground: the rise and the level distance crossed
    # No check here passes or fails: the lines say what was reached.
    J0 = (-4500.0, -1000.0)        # T8.B2 starts here heading +X: 95 m of platform ahead, nothing overhead
    J_STOP_X = 3600.0

    def mana(self):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(self.char)
            x = asc.get_gameplay_attribute_value(self.attrs['Mana'])
            return round(float(x[0] if isinstance(x, tuple) else x), 2)
        except Exception:  # noqa: BLE001
            self.err('mana')
            return None

    def look_to(self, target, pitch=None):
        """the control rotation (the mouse) from the character toward the world point target"""
        rot = unreal.MathLibrary.find_look_at_rotation(self.char.get_actor_location(), unreal.Vector(*target))
        self.pc.set_control_rotation(unreal.Rotator(0.0, rot.pitch if pitch is None else float(pitch), rot.yaw))

    def log_size(self):
        try:
            p = find_log()
            return os.path.getsize(p) if p else 0
        except Exception:  # noqa: BLE001
            return 0

    def log_from(self, off, keys, limit=20):
        try:
            p = find_log()
            if not p:
                return []
            with open(p, 'rb') as f:
                f.seek(off)
                txt = f.read().decode('utf-8', 'replace')
            return [ln.strip()[:240] for ln in txt.splitlines() if any(k in ln for k in keys)][:limit]
        except Exception:  # noqa: BLE001
            self.err('log_from')
            return []

    def start_t8_boost(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.teleport(self.ship, SPAWN, 0.0)
        if 'IA_Space' not in self.act:
            self.act['IA_Space'] = unreal.load_asset(IA_LMB_PATH.rsplit('/', 1)[0] + '/IA_Space')
        self.cmd('Log LogJumpHover Verbose')
        self.cmd('Log LogAbilitySystem Verbose')
        self.D.update({'st': 'ground', 'trk': [], 'jtrk': [], 'log0': self.log_size()})

    def ph_t8_boost(self, el):
        D, s = self.D, self.ship
        st = D['st']
        info = self.char_info(self.char) or {}
        mode = info.get('mode')
        rel = self.char_rel()
        loc = v3(self.char.get_actor_location())
        vel = v3(self.char.get_velocity())
        if st not in ('ground', 'done') and int(el * 5) != D.get('_k'):
            D['_k'] = int(el * 5)
            (D['jtrk'] if st.startswith('j') else D['trk']).append((r(el, 2), st, r(loc, 0), mode, r(vel, 0), self.mana()))
        if st == 'ground':
            if el >= 0.4 and 'g' not in D:
                seat, _ = self.helm_geo()
                D['seat'] = seat
                top = self.world_of(s, [seat[0] - 100.0, -1500.0, 0.0])
                own = [s, self.char] + self.turrets(s)
                g = self.trace(top, [top[0], top[1], top[2] - 6000.0], own)
                if not g or not g.get('at'):
                    D['fail'] = 'no ground 15 m to port of the helm: %s' % g
                    D['st'] = 'done'
                else:
                    D['g'] = g['at']
                    D['p0'] = [g['at'][0], g['at'][1], g['at'][2] + self.char_hh() + 2.0]
                    self.tp_char(D['p0'], 90.0)
            if 'g' in D and el >= 1.4:
                deck = self.deck_hit(s, D['seat'][0] - 100.0, -150.0)
                D['deck_z'] = self.rel(s, deck)[2] if deck else D['seat'][2]
                D['start'] = {'loc': r(loc, 0), 'mode': mode, 'mana': self.mana(), 'health': self.health(self.char),
                              'deck_above_cm': r(deck[2] - D['g'][2], 0) if deck else None}
                # up outboard of the rail (3 m off the hull's side, 4.5 m over the planks), then in over the planks 1 m behind
                # and 1.5 m to port of the pilot's standing spot
                D['w1'] = self.world_of(s, [D['seat'][0] - 100.0, -1100.0, D['deck_z'] + 450.0])
                D['w2'] = self.world_of(s, [D['seat'][0] - 100.0, -150.0, D['deck_z'] + 160.0 + self.char_hh()])
                D['st'], D['t_try'] = 'dash', el + 0.3
        elif st == 'dash':
            # Shift + W on the ground for 2 s, the view level toward the ship: what the boost does there
            t = el - D['t_try']
            self.pc.set_control_rotation(unreal.Rotator(0.0, 0.0, 90.0))
            if 0.0 <= t < 2.0:
                self.inject('IA_Shift')
                self.inject('IA_Move')
                D['dash_v'] = max(D.get('dash_v', 0.0), math.hypot(vel[0], vel[1]))
                D.setdefault('dash_modes', set()).add(mode)
            elif t >= 2.0 and 'dash' not in D:
                D['dash'] = {'top_speed_cms': r(D.get('dash_v'), 0), 'modes': sorted(D.get('dash_modes') or []), 'moved_cm': r(dist(loc, D['p0']), 0),
                             'mana': self.mana()}
            elif t >= 2.8:                     # keys up for 0.8 s, then back to the start spot
                self.tp_char(D['p0'], 90.0)
                D['st'], D['t_hop'], D['hops'] = 'hop', el + 0.8, []
        elif st == 'hop':
            # Space, Space at the top, Space at the next top (jump, air jump, hover: MOVE_Flying), then Shift + W
            t = el - D['t_hop']
            hops = D['hops']
            since = el - D.get('t_press', -1e9)
            self.look_to(D['w1'])

            def press(what):
                self.inject('IA_Space')
                hops.append({'t': r(t, 2), 'what': what, 'mode': mode, 'feet_above_ground_cm': r(loc[2] - self.char_hh() - D['g'][2], 0)})
                D['t_press'] = el
            if not hops:
                if t >= 0.0 and mode == 'MOVE_WALKING':
                    press('jump')
            elif len(hops) < 3:
                if since >= 0.2 and vel[2] <= 10.0:
                    press('air jump' if len(hops) == 1 else 'hover')
            elif mode == 'MOVE_FLYING' and since >= 0.3:
                D['boost_keys'] = 'Space, Space, Space (hover), then Shift + W held'
                D['hover_at_cm'] = r(loc[2] - self.char_hh() - D['g'][2], 0)
                D['st'], D['t_fly'] = 'fly1', el
            if t >= 8.0 and D['st'] == 'hop':
                D['fail'] = 'no hover (MOVE_Flying) 8 s after the jump keys: %s, presses %s' % (mode, hops)
                D['st'], D['t_j'] = 'j_setup', el
        elif st == 'fly1':
            # Shift held all the way (the boost stays on). The view is the thrust direction and W the thrust: at the velocity
            # that leads to the next point (its distance x 1.2 per second, at most 9 m/s), W only while the velocity is more
            # than 1.2 m/s off that. In the air the character barely brakes by itself (run 3: still 13.9 m/s one second
            # after the keys were let go, 17 m higher), so stopping is thrust against the motion, as a player would steer.
            # Two points: outboard of the rail 4.5 m over the planks, then 1.6 m over the planks behind the helm.
            feet = loc[2] - self.char_hh() - D['g'][2]
            sp = math.sqrt(sum(x * x for x in vel))
            D['vmax'] = max(D.get('vmax', 0.0), sp)
            D['zmax'] = max(D.get('zmax', -1e9), feet)
            D['climb_v'] = max(D.get('climb_v', 0.0), vel[2])
            here = {'rel': r(rel, 0), 'mode': mode, 'mana': self.mana(), 'fly_s': r(el - D['t_fly'], 2), 'above_ground_cm': r(feet, 0),
                    'speed_cms': r(sp, 0)}
            leg = D.setdefault('leg', 1)
            tgt = D['w1'] if leg == 1 else D['w2']
            dv = [tgt[i] - loc[i] for i in range(3)]
            dd = math.sqrt(sum(x * x for x in dv)) or 1.0
            vd = min(900.0, 1.2 * dd)
            err = [dv[i] / dd * vd - vel[i] for i in range(3)]
            self.inject('IA_Shift')
            if math.sqrt(sum(x * x for x in err)) > 120.0:
                rot = unreal.MathLibrary.find_look_at_rotation(unreal.Vector(0.0, 0.0, 0.0), unreal.Vector(*err))
                self.pc.set_control_rotation(unreal.Rotator(0.0, rot.pitch, rot.yaw))
                self.inject('IA_Move')
                D['thrust_frames'] = D.get('thrust_frames', 0) + 1
            if mode != 'MOVE_FLYING' and el >= D['t_fly'] + 0.3:
                D['ended'] = dict(here, leg=leg)           # with Shift still held (out of mana?)
                D['st'], D['t_rel'] = 'land', el
            elif leg == 1 and dd < 200.0 and sp < 500.0:
                D['leg'], D['at_w1'] = 2, here
            elif leg == 2 and math.hypot(dv[0], dv[1]) < 70.0 and abs(dv[2]) < 150.0 and sp < 200.0:
                D['st'], D['t_rel'], D['at_release'] = 'land', el, here
            elif el >= D['t_fly'] + 40.0:
                D['timeout'] = dict(here, leg=leg)
                D['st'], D['t_rel'] = 'land', el
            elif el >= D['t_fly'] + 3.0 and D.get('vmax', 0.0) < 100.0:
                D['fail'] = 'hovering, but 3 s of Shift + W did not move the character (%s)' % here
                D['st'], D['t_rel'] = 'land', el
        elif st == 'land':                     # no key held: Shift is released; one Space drops out of the hover
            if mode == 'MOVE_FLYING' and el >= D['t_rel'] + 0.8 and 'unhover' not in D:
                D['unhover'] = {'rel': r(rel, 0), 'speed_cms': r(math.sqrt(sum(x * x for x in vel)), 0), 'mana': self.mana()}
                self.inject('IA_Space')
            if mode == 'MOVE_WALKING' and el >= D['t_rel'] + 0.2:
                fod = self.feet_over_deck(rel)
                on_deck = fod[0] is not None and fod[0] < 15.0
                D['landed'] = {'rel': r(rel, 0), 'feet_over_deck': fod, 'base': self.char_base(), 't': r(el - D['t_rel'], 2), 'on_deck': on_deck,
                               'mana': self.mana(), 'health': self.health(self.char)}
                if on_deck:
                    D['st'], D['t_walk'] = 'walk', el
                else:
                    D['st'], D['t_j'] = 'j_setup', el
            elif el >= D['t_rel'] + 10.0:
                D['fail'] = 'not walking 10 s after Shift was released (hull %s, %s)' % (r(rel, 0), mode)
                D['st'], D['t_j'] = 'j_setup', el
        elif st == 'walk':
            d = math.hypot(rel[0] - D['seat'][0], rel[1] - D['seat'][1])
            self.look_to(self.world_of(s, [D['seat'][0], D['seat'][1], rel[2]]), -8.0)
            if d > 50.0:
                self.inject('IA_Move')
            if d <= 50.0 or el >= D['t_walk'] + 6.0:
                D['at_wheel'] = {'rel': r(rel, 0), 'seat_h_cm': r(d, 0), 'walk_s': r(el - D['t_walk'], 2)}
                D['st'], D['t_f'] = 'f', el + 0.3
        elif st == 'f':
            if el >= D['t_f'] and 'f' not in D:
                D['f'] = el
                self.inject('IA_AirshipBoard')
                self.event('inject', what='IA_AirshipBoard (at the wheel after the boost flight)')
            if 'f' in D and el >= D['f'] + 0.6:
                D['boarded'] = same(self.pawn(), s)
                self.capture('t8_boost', 'helm', s)
                if D['boarded']:
                    self.cmd('Aura.Airship.Exit 0')
                D['st'], D['t_j'] = 'j_setup', el
        elif st == 'j_setup':
            if 'jtp' not in D:
                if el >= D['t_j'] + 0.6:
                    D['jtp'] = el
                    D['mana_before_wait'] = self.mana()
                    gz = D['g'][2] if 'g' in D else 0.0
                    self.tp_char([self.J0[0], self.J0[1], gz + self.char_hh() + 2.0], 0.0)
                    self.pc.set_control_rotation(unreal.Rotator(0.0, 0.0, 0.0))
            elif el >= D['jtp'] + 3.0:         # 3 s standing: shows whether mana comes back by itself
                D['j0'] = {'loc': r(loc, 0), 'mode': mode, 'mana': self.mana(), 'mana_3s_before': D.get('mana_before_wait')}
                D['st'], D['t_run'], D['presses'] = 'j_run', el, []
        elif st == 'j_run':
            self.pc.set_control_rotation(unreal.Rotator(0.0, 0.0, 0.0))
            self.inject('IA_Move')
            t = el - D['t_run']
            presses = D['presses']
            feet = loc[2] - self.char_hh()
            since = el - D.get('t_press', -1e9)

            def press(what):
                self.inject('IA_Space')        # one frame: a key press (the next frame without it is the release)
                presses.append({'t': r(t, 2), 'what': what, 'loc': r(loc, 0), 'mode': mode, 'vz': r(vel[2], 0), 'mana': self.mana()})
                D['t_press'] = el
            if not presses:
                if t >= 0.8 and mode == 'MOVE_WALKING':
                    D['take_off'] = {'loc': r(loc, 0), 'feet_z': r(feet, 1), 'speed_cms': r(math.hypot(vel[0], vel[1]), 0)}
                    press('jump')
                elif t >= 5.0:
                    D['jfail'] = 'not walking 5 s after W (%s)' % mode
                    D['st'] = 'done'
            else:
                D['jz'] = max(D.get('jz', -1e9), feet - D['take_off']['feet_z'])
                n = len(presses)
                if mode == 'MOVE_WALKING' and since >= 0.3:
                    D['j_land'] = {'loc': r(loc, 0), 'air_s': r(t - presses[0]['t'], 2), 'gap_cm': r(loc[0] - D['take_off']['loc'][0], 0),
                                   'mana': self.mana()}
                    D['st'] = 'done'
                elif n == 1 and since >= 0.2 and vel[2] <= 10.0:
                    press('air jump')
                elif n == 2 and since >= 0.2 and vel[2] <= 10.0:
                    press('hover')
                elif n == 3 and since >= 0.3 and (loc[0] >= self.J_STOP_X or since >= 14.0):
                    D['hover_cut'] = 'the harness ended the hover (%s)' % ('the platform ends' if loc[0] >= self.J_STOP_X else '14 s')
                    press('stop hover')
                elif t >= 45.0:
                    D['jfail'] = 'still in the air after 45 s (%s)' % mode
                    D['st'] = 'done'
        if D['st'] == 'done':
            D['phase_done'] = True

    def end_t8_boost(self):
        D = self.D
        self.cmd('Log LogJumpHover Log')
        self.cmd('Log LogAbilitySystem Log')
        logs = self.log_from(D.get('log0', 0), ('LogJumpHover', 'Boost'), 24)
        start, landed = D.get('start') or {}, D.get('landed') or {}
        fly = [x for x in D.get('trk') or [] if x[1] == 'fly1']
        drain = None
        if len(fly) >= 2 and fly[-1][0] > fly[0][0] and fly[0][5] is not None and fly[-1][5] is not None:
            drain = r((fly[0][5] - fly[-1][5]) / (fly[-1][0] - fly[0][0]), 2)
        reached = bool(landed.get('on_deck'))
        self.check('T8.B1_boost_to_deck', 'INFO', 'REACHED THE PLANKS: %s, AT THE HELM BY F: %s. The player on the ground 15 m to port of the helm of the '
                   'parked ship (%s; the planks %s cm above the ground), the game\'s own keys only. Shift + W on the ground for 2 s (the '
                   'boost there is a run, not a flight): %s. Flight: %s; presses %s; hovering %s cm above the ground. Shift held, the view '
                   'as the thrust direction and W as the thrust (toward the next point at its distance x 1.2 per second, at most 9 m/s; W on '
                   'in %s frames): at the point 3 m off the rail and 4.5 m over the planks %s; at the point 1.6 m over the planks behind the '
                   'helm, slower than 2 m/s, keys let go: %s; Space to drop out of the hover: %s. Top speed %s cm/s, fastest climb %s cm/s, '
                   'mana %s per s, highest point %s cm above the ground. The flight ended by itself with the keys held: %s; 40 s limit: %s. '
                   'Landed: %s. W to the wheel: %s%s' % (
                       reached, D.get('boarded'), start, start.get('deck_above_cm'), D.get('dash'), D.get('boost_keys'), D.get('hops'),
                       D.get('hover_at_cm'), D.get('thrust_frames'), D.get('at_w1'), D.get('at_release'), D.get('unhover'),
                       r(D.get('vmax'), 0) if D.get('vmax') is not None else None, r(D.get('climb_v'), 0) if D.get('climb_v') is not None else None, drain,
                       r(D.get('zmax'), 0) if D.get('zmax') is not None else None, D.get('ended'), D.get('timeout'), landed,
                       D.get('at_wheel'), ('; NOTE: ' + D['fail']) if D.get('fail') else ''),
                   {'start': start, 'w1': D.get('at_w1'), 'release': D.get('at_release'), 'ended': D.get('ended'), 'landed': landed,
                    'wheel': D.get('at_wheel'), 'boarded': D.get('boarded'), 'fail': D.get('fail'), 'dash': D.get('dash'), 'hops': D.get('hops'),
                    'unhover': D.get('unhover'), 'track': D.get('trk'), 'log': logs})
        jt = D.get('jtrk') or []
        presses, to, jl = D.get('presses') or [], D.get('take_off') or {}, D.get('j_land') or {}
        hov = None
        hp = next((p for p in presses if p['what'] == 'hover'), None)
        if hp and to:
            t0 = D['t_run'] + hp['t']
            seg = [x for x in jt if x[0] >= t0 + 0.3 and x[3] != 'MOVE_WALKING' and abs(x[4][2]) < 30.0]
            if len(seg) >= 2:
                dt = seg[-1][0] - seg[0][0]
                hov = {'s': r(dt, 1), 'cm': r(seg[-1][2][0] - seg[0][2][0], 0), 'cms': r((seg[-1][2][0] - seg[0][2][0]) / dt, 0) if dt > 0 else None,
                       'mana': [seg[0][5], seg[-1][5]], 'mana_per_s': r((seg[0][5] - seg[-1][5]) / dt, 2) if dt > 0 and seg[0][5] is not None and seg[-1][5] is not None else None,
                       'modes': sorted(set(x[3] for x in seg)), 'feet_over_take_off_cm': [r(seg[0][2][2] - self.char_hh() - to.get('feet_z', 0.0), 0),
                                                                                         r(seg[-1][2][2] - self.char_hh() - to.get('feet_z', 0.0), 0)]}
        self.check('T8.B2_jump_hover_gap', 'INFO', 'on the open platform with W held (GA_JumpHover on Space, the real key): standing 3 s first, mana '
                   '%s -> %s; take-off %s; presses %s; highest rise of the feet %s cm; level flight after the hover press: %s%s; back on the '
                   'ground %s: LEVEL GAP CROSSED %s cm in %s s in the air%s' % (
                       (D.get('j0') or {}).get('mana_3s_before'), (D.get('j0') or {}).get('mana'), to, presses,
                       r(D.get('jz'), 1) if D.get('jz') is not None else None, hov, (' (' + D['hover_cut'] + ')') if D.get('hover_cut') else '', jl,
                       jl.get('gap_cm'), jl.get('air_s'), ('; NOTE: ' + D['jfail']) if D.get('jfail') else ''),
                   {'j0': D.get('j0'), 'take_off': to, 'presses': presses, 'rise_cm': D.get('jz'), 'hover': hov, 'land': jl, 'track': jt,
                    'log': [x for x in logs if 'LogJumpHover' in x]})
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.tp_char(CHAR_FOOT, 0.0)

    # ---- T8.11 (S, review 2026-11-27, should fix 6): the helm of a ship whose deck is the hull's collision (no physics asset
    # bodies: an old or empty PA_Airship). Players then stand on the hull's lid, 1.2-2.9 m above the planks and the seat;
    # IsWithinHelmReach measured the height from the seat, so F never took the helm there. AAirshipPawn::
    # SetDeckOnPhysicsAsset(false) puts ship 1 in that state for the phase (the same code path as no bodies).
    def start_t8_lid(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.teleport(self.ship, SPAWN, 0.0)

    def ph_t8_lid(self, el):
        D, s = self.D, self.ship
        if el >= 0.4 and 'off' not in D:
            D['off'] = True
            D['was'] = bool(call(s, 'is_deck_on_physics_asset'))
            try:
                s.set_deck_on_physics_asset(False)
            except Exception:  # noqa: BLE001
                self.err('set_deck_on_physics_asset')
            D['now'] = bool(call(s, 'is_deck_on_physics_asset'))
        if el >= 0.7 and 'tp' not in D and 'off' in D:
            D['tp'] = True
            seat, _ = self.helm_geo()
            D['seat'] = seat
            loc, traced = self.deck_point(s, seat[0] - 80.0, seat[1])      # deck_comp: the hull's collision now
            D['traced'] = traced
            self.tp_char(loc, s.get_actor_rotation().yaw)
        if el >= 2.0 and 'f' not in D and 'tp' in D:
            rel = self.char_rel()
            D['f'] = {'rel': r(rel, 1), 'feet_over_seat_cm': r(rel[2] - self.char_hh() - D['seat'][2], 1),
                      'seat_h_cm': r(math.hypot(rel[0] - D['seat'][0], rel[1] - D['seat'][1]), 1),
                      'mode': (self.char_info(self.char) or {}).get('mode'), 'base': self.char_base()}
            self.inject('IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (on the hull lid behind the wheel)')
        if 'f' in D and el >= 2.7 and 'res' not in D:
            D['res'] = {'boarded': same(self.pawn(), s)}
            if D['res']['boarded']:
                self.cmd('Aura.Airship.Exit 0')
        if 'res' in D and el >= 3.5:
            D['phase_done'] = True

    def end_t8_lid(self):
        D = self.D
        back = None
        try:
            self.ship.set_deck_on_physics_asset(True)
            back = bool(call(self.ship, 'is_deck_on_physics_asset'))
        except Exception:  # noqa: BLE001
            self.err('set_deck_on_physics_asset_back')
        reach_h = None
        try:
            reach_h = float(self.settings().get_editor_property('HelmReachHeight'))
        except Exception:  # noqa: BLE001
            self.err('helm_reach_height')
        f, res = D.get('f') or {}, D.get('res') or {}
        ok = (D.get('was') is True and D.get('now') is False and bool(D.get('traced')) and f.get('feet_over_seat_cm') is not None and reach_h is not None
              and f['feet_over_seat_cm'] > reach_h and res.get('boarded') is True and back is True)
        self.check('T8.11_helm_on_hull_deck_S', 'PASS' if ok else 'FAIL', 'ship 1 with the deck on the hull\'s collision (SetDeckOnPhysicsAsset false: '
                   'IsDeckOnPhysicsAsset %s -> %s), the player on the lid 80 cm behind the standing spot (traced %s): %s; the feet are %s cm '
                   'above the seat (HelmReachHeight %s: measured from the seat F was refused); F: at the helm %s (want True); the deck back on '
                   'the physics asset afterwards: %s' % (D.get('was'), D.get('now'), D.get('traced'), f, f.get('feet_over_seat_cm'), reach_h,
                                                         res.get('boarded'), back), {'f': f, 'res': res})
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.tp_char(CHAR_FOOT, 0.0)

    # ---- T8.12 (S, review 2026-11-27, nit 9): a ship that goes away under its pilot (AAirshipPawn::EndPlay, Destroyed: the
    # console, kill Z) throws him clear like the crew of a ship shot down. Leaving with F keeps the place at the wheel; that
    # path here would set the character walking on planks that are gone a moment later. A third ship (Aura.Airship.Spawn),
    # low over the platform, the player at its helm (Board 0 from its deck: the nearest free ship), then K2_DestroyActor.
    GONE3 = (1000.0, -2500.0, 700.0)

    def ships_now(self):
        return unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, SHIP_CLS))

    def start_t8_gone(self):
        if same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Exit 0')
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['before'] = set(a.get_name() for a in self.ships_now())
        self.cmd('Aura.Airship.Spawn')

    def ph_t8_gone(self, el):
        D = self.D
        if 's3' not in D:
            for a in self.ships_now():
                if a.get_name() not in D['before']:
                    D['s3'], D['s3_name'] = a, a.get_name()
            return
        s3 = D['s3']
        if el >= 1.0 and 'parked' not in D:
            D['parked'] = True
            self.wind_off(s3)
            self.teleport(s3, self.GONE3, 0.0)
        if el >= 2.0 and 'tp' not in D:
            D['tp'] = True
            seat = v3(s3.get_pilot_seat_location())
            self.tp_char([seat[0] - 60.0, seat[1], seat[2] + self.char_hh() + 30.0], 0.0)
        if el >= 3.0 and 'b' not in D:
            D['b'] = True
            self.cmd('Aura.Airship.Board 0')
        if el >= 4.0 and 'k' not in D:
            D['k'] = el
            D['tur'] = self.turrets(s3)
            D['pre'] = {'at_the_helm_of_ship3': same(self.pawn(), s3), 'health': self.health(self.char), 'turrets': len(D['tur']),
                        'char_loc': r(v3(self.char.get_actor_location()), 0)}
            try:
                s3.destroy_actor()
            except Exception:  # noqa: BLE001
                self.err('destroy_ship3')
        if 'k' in D and 'post1' not in D and el >= D['k'] + 0.2:
            info = self.char_info(self.char) or {}
            D['post1'] = {'pawn_is_char': same(self.pawn(), self.char), 'mode': info.get('mode'), 'vel': r(v3(self.char.get_velocity()), 0),
                          'att': info.get('att'), 'loc': info.get('loc'), 'health': info.get('health'), 'ship3_valid': bool(valid(s3)),
                          'turrets_left': len([t for t in D['tur'] if valid(t)])}
        if 'post1' in D and el >= D['k'] + 4.5:
            info = self.char_info(self.char) or {}
            D['post2'] = {'mode': info.get('mode'), 'loc': info.get('loc'), 'health': info.get('health')}
            D['phase_done'] = True

    def end_t8_gone(self):
        D = self.D
        pre, p1, p2 = D.get('pre') or {}, D.get('post1') or {}, D.get('post2') or {}
        up = float(gp(self.ship, 'EjectUpSpeed', 'eject_up_speed') or 1200.0)
        vz = (p1.get('vel') or [0, 0, 0])[2]
        ok = (pre.get('at_the_helm_of_ship3') is True and p1.get('pawn_is_char') is True and p1.get('mode') == 'MOVE_FALLING' and p1.get('att') is None
              and vz >= 0.5 * up and p1.get('ship3_valid') is False and p1.get('turrets_left') == 0 and p1.get('health') == pre.get('health')
              and (p2.get('health') or 0.0) > 0.0)
        self.check('T8.12_destroyed_ship_ejects_pilot_S', 'PASS' if ok else 'FAIL', 'a third ship (%s) at %s with the player at its helm (%s), then '
                   'destroyed (K2_DestroyActor): 0.2 s later %s (want the character possessed again, MOVE_FALLING, not attached, thrown up: vz >= '
                   '%s = half of EjectUpSpeed %s after 0.2 s of gravity; left in place it would be <= 0; the ship and its %s turrets gone, health '
                   'as before); 4.5 s later %s' % (D.get('s3_name'), self.GONE3, pre, p1, r(0.5 * up, 0), up, pre.get('turrets'), p2),
                   {'pre': pre, 'post1': p1, 'post2': p2})
        self.tp_char(CHAR_FOOT, 0.0)

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
            t = self.tele(self.ship)
            self.D['v_exit'] = t.get('ForwardSpeedMS')
            self.D['thr_exit'] = t.get('Throttle')
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
        # No reverse from the drift: the shaped throttle once the pilot's last command has decayed. The harness teleports the
        # piloted ship to 48 m/s with no pilot input, so Galleon's boarding STOP order and Classic's v1 brake command reverse
        # (-0.5 .. -0.7) before the exit; the shaping lag (time constant ~0.25 s) carries that into the first second after
        # the exit (decay time constant measured 0.25 s Galleon, 0.45 s Classic). The drift's own command is what the
        # throttle settles to: from 3 s after the exit (>= 6.6 time constants: < 0.2 % of the pre-exit value left). The
        # whole-track minimum and the values at the exit and the first sample are reported too, and the throttle must only
        # recover (never go more negative) between the exit and then.
        rev_all = min((x[5] for x in trk if x[5] is not None), default=None)
        rev = min((x[5] for x in trk if x[5] is not None and x[0] >= 3.7), default=None)
        neg = [x[5] for x in trk if x[5] is not None and x[0] < 3.7]
        recovers = all(neg[i + 1] >= neg[i] - 0.005 for i in range(len(neg) - 1))
        ok = modes == [2] and v_late is not None and abs(v_late - 2.5) <= 0.3 and dyaw is not None and dyaw < 2.0 and (rev is None or rev >= -0.01) and recovers
        key = 'T9.1_drift_P&F' if s == 3 else 'T9.2_drift_%s' % name
        self.check(key, 'PASS' if ok else 'FAIL', '%s: exit at %s m/s; modes %s (want [2] Drift), speed %s m/s from 30 s (want 2.5 +-0.3), heading '
                   'change %s deg (want < 2), lowest shaped throttle from 3 s after the exit %s (want >= 0: no reverse, the fans idle; '
                   'at the exit (piloted) %s, first sample %s, whole-track minimum %s = the pilot\'s pre-exit command decaying, recovering only: %s)' % (
                       name, self.D.get('v_exit'), modes, r(v_late, 2) if v_late is not None else None, r(dyaw, 2) if dyaw is not None else None, rev,
                       self.D.get('thr_exit'), neg[0] if neg else None, rev_all, recovers),
                   {'track': trk[::10], 'first_s': trk[:30]})
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
        # The player stays on the start platform: riding ship 1's deck it would be carried 0.8 km away, and t7_caps's
        # teleport of the ship leaves a rider behind (Board then picks the nearest ship: ship 2)
        self.tp_char(CHAR_FOOT, 0.0)
        self.teleport(self.ship, SPAWN, 0.0)
        self.D['trk'] = []

    def ph_t9_input(self, el):
        if el >= 0.5 and 'in' not in self.D:
            self.D['in'] = True
            self.cmd('Aura.Airship.Input 1 0')
            # The command flies EVERY ship of the world: ship 2 (parked, the later phases' dummy) is cleared again in the
            # same frame, so it never moves
            try:
                if valid(self.ship2):
                    self.ship2.debug_clear_input()
            except Exception:  # noqa: BLE001
                self.err('ship2_clear')
        if el >= 6.5 and 'clr' not in self.D:
            self.D['clr'] = True
            self.cmd('Aura.Airship.InputClear')
        t = self.tele(self.ship)
        self.D['trk'].append((r(el, 2), t.get('UnpilotedMode'), t.get('SpeedMS')))
        # Coast from ~48 m/s is the v1 drag alone (about 1/17 s^-1, ~45 s to 3 m/s): the phase runs until the Hold is seen
        # (+2 s), at most 75 s
        if 'clr' in self.D and t.get('UnpilotedMode') is not None and int(t.get('UnpilotedMode')) == 3 and el >= 6.6:
            self.D.setdefault('hold_el', el)
            if el >= self.D['hold_el'] + 2.0:
                self.D['phase_done'] = True

    def end_t9_input(self):
        trk = self.D['trk']
        during = sorted(set(int(x[1]) for x in trk if 1.0 <= x[0] < 6.4 and x[1] is not None))
        after = [x for x in trk if x[0] >= 6.6 and x[1] is not None]
        first = int(after[0][1]) if after else None
        v_clear = after[0][2] if after else None
        hold = next((x for x in after if int(x[1]) == 3), None)
        ok = during == [0] and (first == 1 or (v_clear is not None and v_clear < 3.0 and first == 3)) and hold is not None and (hold[2] or 0) < 3.0 \
            and int(after[-1][1]) == 3
        p2 = v3(self.ship2.get_actor_location()) if valid(self.ship2) else None
        self.check('T9.6_debug_input_then_coast', 'PASS' if ok else 'FAIL', 'Aura.Airship.Input 1 0: modes %s (want [0] None); cleared at %s m/s: first '
                   'mode %s (want 1 Coast), Hold at %s (want once below 3 m/s), final %s; coast took %s s; ship 2 (cleared at once) %s cm from its '
                   'parking spot' % (during, v_clear, first, hold[:3] if hold else None, after[-1][1] if after else None,
                                     r(hold[0] - 6.5, 1) if hold else None, r(dist(p2, PARK2), 0) if p2 else None),
                   {'track': trk[::15]})

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
            att = bool(valid(c) and c.get_attach_parent_actor() is not None)
            rel = v3(unreal.MathLibrary.inverse_transform_location(ship.get_actor_transform(), unreal.Vector(*com))) if com else None
            self.D['trk'].append((r(el - self.D['k_t'], 3), r(v, 1), r(w, 2), r(com, 0) if com else None, att, r(rel, 0) if rel else None))
            if 'resp' not in self.D and valid(mesh) and el >= self.D['k_t'] + 0.2:
                try:
                    self.D['resp'] = en(mesh.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PHYSICS_BODY))
                    self.D['sim'] = bool(mesh.is_simulating_physics('None'))
                    # every part of the body that simulates now (KeepCorpseOffHull's rule covers all of them)
                    sims = []
                    for comp in c.get_components_by_class(unreal.PrimitiveComponent):
                        try:
                            if comp.is_simulating_physics('None'):
                                sims.append((comp.get_name(), en(comp.get_collision_response_to_channel(unreal.CollisionChannel.ECC_PHYSICS_BODY))))
                        except Exception:  # noqa: BLE001
                            pass
                    self.D['sims'] = sims
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
        rise_seat = max(((x[3][2] - com0[2]) for x in trk if x[3] and com0), default=None)
        # "Thrown up" is physics after the dismount: the death's dismount first PLACES the body at the station's exit point
        # (CannonExitOffset 120 cm inboard, then onto the deck there: the planks' boxes since the helm / deck change, the
        # UCX lid 1.2-2.9 m over them before), a set move, not a throw. The rise is measured from the first sample after
        # the detach.
        det = [x for x in trk if x[3] and not x[4]]
        rise = max((x[3][2] - det[0][3][2] for x in det), default=None) if det else None
        sims = self.D.get('sims')
        # The ignore rule matters only for parts that simulate. BP_MyCharMech dies with its Control Rig ragdoll and the
        # disintegration (no physics-simulating mesh): then nothing can touch the hull and the rule has nothing to change.
        if sims:
            resp_ok = all(rr == 'ECR_IGNORE' for _, rr in sims)
            resp_txt = 'simulating parts %s (want ECR_IGNORE to PhysicsBody)' % sims
        else:
            resp_ok = True
            resp_txt = ('no part simulates physics (mesh simulating %s, mesh response %s): the mech dies with its Control Rig ragdoll and the '
                        'disintegration, nothing can push the hull, the ignore rule has nothing to change (log: 0 simulated parts)' % (self.D.get('sim'), self.D.get('resp')))
        hang = None
        if det and det[-1][5] and det[0][5]:
            hang = r(dist(det[-1][5], det[0][5]), 0)
        ok = (resp_ok and dv is not None and dv < 50.0 and dw is not None and dw < 2.0 and rise is not None and rise < 100.0
              and post.get('gunner') is None and post.get('att') is None and (post.get('health') or 0.0) <= 0.0)
        self.check('T5.15_dead_gunner_ragdoll_S', 'PASS' if ok else 'FAIL', 'respawned player on R1 of %s, killed there: %s; hull speed change max %s cm/s '
                   '(want < 50), spin change max %s deg/s (want < 2); body centre of mass rose at most %s cm after the dismount placed it (want < 100: '
                   'not thrown; %s cm above the seat incl. the placement on the deck); after 2.6 s %s (want station free, detached, dead); the body '
                   'moved %s cm relative to the hull after the detach (it stays where it died while the ship moves on)' % (
                       self.D['ship'].get_name(), resp_txt, r(dv, 1) if dv is not None else None,
                       r(dw, 2) if dw is not None else None, r(rise, 0) if rise is not None else None, r(rise_seat, 0) if rise_seat is not None else None,
                       post, hang), {'track': trk[::3], 'pre': pre, 'sims': sims})


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
        L.append('hit_info read failures: %s' % R.get('hit_info_err'))
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
