# as_62_pie_swarm.py - round 2 PIE harness with a REAL Mech Sentinel swarm (Docs/Airship/round2/SPEC_A.md D3 / D4, the
# swarm rows T3.5 and T6.7 that as_59 skips): STANDALONE, one player on L_AirshipTest, fixed 30 fps game time, a
# frame-by-frame state machine (Slate post-tick callback) armed from the inbox like as_59; it returns at once and the
# world ticks between inbox calls. No Aura.MechSentinel.TestBullet: every bullet comes from the swarm's own combat
# processor (target = the PlayerState's pawn, ranged attack, FireSentinelBullet, TickBullets: Pawn sweep, then the
# tagged-target Visibility fallback and UMechSentinelSwarmSubsystem::BulletTargetRedirect).
# Since the helm / deck change (2026-11-25, SPEC_A.md 6.8) the hull's convexes ignore Pawn and Visibility: what a bullet
# meets is the Mesh's physics-asset boxes (object type Pawn, block Visibility; actor = the ship), a turret's HitBox
# (WorldDynamic, blocks Visibility; actor = the turret) or a character's capsule. A driven ship is "player controlled",
# so the Pawn sweep damages it at its first PA box; an undriven one only through the tagged path.
# Run (L_AirshipTest open, no PIE, the round-2 C++ built and as_51..as_57 run):
#   Docs/Airship/scripts/harness/inbox.sh 62 Docs/Airship/scripts/ue/as_62_pie_swarm.py 60
#   status: inbox.sh 62s Docs/Airship/scripts/ue/as_62s_status.py 30     stop: inbox.sh 62x Docs/Airship/scripts/ue/as_62x_stop.py 30
#   or the whole session: _AirshipWork_logs/run_r2_swarm.sh (lock, launch, run, poll, quit, release)
# Results: Saved/Airship/round2_swarm/sw_result.json (checks with the measured values, events, kills, 5 Hz series),
#   sw_report.txt, sw_log.txt, sw_status.txt (rewritten every 2 s), sw_restore.json; captures
#   Saved/Airship/captures/round2_swarm/.
# The swarm: TEMP_AS62_Spawner, an AMechSentinelWaveSpawner placed in the editor level before PIE (Python can't spawn
# actors in a PIE world) with EntityConfig = /Game/MechSentinel/Data/DA_MechSentinelConfig, AdvanceMode WhenCleared,
# bAutoStart off, no fallback point, two waves of its own (wave 1: AS62_COUNT sentinels at full stats; wave 2:
# AS62_COUNT_D at AS62_D_HEALTH x health, so the turrets can kill some in the time). Each phase that needs a fresh swarm
# calls DespawnAll(false) and, frames later, StartWaveAtPoints([point], wave, None) on the PIE copy. The swarm rules are
# the GameMode's (BP_MyGameMode -> DA_MechSentinelSwarmRules). Sentinels are read on the server through
# UMechSentinelCombatLibrary::FindSentinelsInCapsule + GetSentinelInfo (location, state, health) and the subsystem's
# OnSentinelKilled / OnSentinelDamaged (bound with add_callable, removed at the end).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, LevelEditorPlaySettings Standalone / 1 player,
# UBurrowerSettings.bEnabled False, LogMechSentinel Verbose (its "Sentinel bullet hit tagged target X" lines count the
# hits of the tagged path per target; back to Log), the UAirshipSettings values read for the checks (not changed).
# TEMP_AS62_Spawner and TEMP_AS62_Capture are removed from the editor level after PIE; the map is never saved. The
# user's own Play ("Repeating last play command" in the log) is never stopped. Ship wind sway off on both ships.
# Between phases the player is topped up with GE_HealthPotion (instant, only when below 70 % health; the crew share
# checks measure inside a phase); below AS62_MIN_HP the phase's sentinels are removed (safety, reported) so the run never
# loses its player to the swarm.
#
# Phases (game seconds) -> checks:
#  settle 3     wind off, scheme, the PIE spawner / swarm / rules / config found, delegates bound   setup_swarm
#  spawn2 3     Aura.Airship.Spawn: ship 2 parked at P2, 50 m to starboard of ship 1's test spot (undriven, unmanned)
#  board 2.5    Aura.Airship.Board 0
#  s_pilot 30   (a) ship 1 hovers at P1, driven; wave 1 spawns 55 m to port      SW.a1 targets (PlayerState pawn = ship 1,
#               (c1) ship 2 parked 50 m to starboard                              the swarm orbits it, attacks); T3.5 hull
#                                                                                 damage from real bullets (+ log: tagged
#                                                                                 hits); SW.a2 pilot = CrewDamageShare x
#                                                                                 ship loss; SW.c1 ship 2 untouched
#  s_gunner 25  (b) Aura.Airship.Exit 0, Mount 0 <AS62_STATION> (turret L) on      SW.b1 target = the gunner (a character
#               ship 1, now undriven                                              with a PlayerState), the swarm re-centres
#                                                                                 on it; SW.b2 ship / turret / gunner
#                                                                                 losses (crew share + direct); SW.b3 the
#                                                                                 turret takes real bullets (redirect)
#  s_empty 22   (c2) Dismount, the player on the start platform 280 m away:      SW.c2 ship 1 (and 2) unchanged over 20 s,
#               ship 1 undriven and unmanned with the swarm around it             the swarm leaves it
#  s_turret 45  (d) DespawnAll, ship 2 parked far, Board 0, ship 1 at P1; wave 2  T6.7 turret rounds hurt sentinels;
#               55 m ahead of the bow. 2.5-9 s and 29-44 s: Aura.Airship.          SW.d3 kills; SW.d1 turret damage from
#               TurretFire 1 at the nearest sentinel in a turret's arc (10 Hz;    the plain geometry (INFO); SW.d2 turret
#               29-44 s: the ship jumps AS62_JUMP_CM back along -X every          damage from real bullets in the holds
#               AS62_JUMP_S, else the orbiting swarm stays behind the turrets).
#               9-29 s, fire off: "holds": the harness keeps the ship placed
#               (teleport every frame, yaw 0) so that one ATTACKING sentinel      (the line meets the turret's
#               stays at hull AS62_HOLD (2900, -395, 1001), ahead and to port of   HitBox directly now: the hull is out of
#               turret 0; its aim line toward the ship's target point (root +      Visibility); SW.d4 pilot crew share again
#               TargetHeightOffset) crosses turret 0's HitBox, which is the first
#               thing on it that blocks Visibility. Why: the swarm orbits the
#               ship's ROOT at 11-19 m and the turrets sit 21 m forward of it, so
#               in a plain hover no aim line crosses a turret; one that does needs
#               a sentinel 25-31 m ahead (inside the attack exit range 31.25 m) at
#               9.5-10.5 m height, 4 m to the side: a spot sentinels only pass
#               through. With Settings.SwarmTurretAimChance > 0 (C++, 2026-11-27)
#               part of the bullets at a driven ship is aimed at a living turret
#               instead: SW.a3 / SW.d1 then count real turret hits without holds.
#  s_cannon 33  (e) DespawnAll, Board 0, ship 1 at P1, wave 1 from port. 9-19 s: 3     SW.e1 the flight sweep: OnSentinelDamaged with
#               test balls of ship 1 (the cannonball class, source = the ship) from     ship 1 as instigator, the sentinel loses health;
#               the nearest muzzle at a sentinel, led. 19-31 s: balls of ship 2 into    SW.e2 the burst's splash: events with ship 2 as
#               ship 1's hull next to a sentinel 1.5-5.6 m off it.                      instigator at a part of the full damage
#  end          log scan (errors, ensures, Accessed None, LogMechSentinel warnings), the tagged-hit counts per phase
# Knobs (inbox globals read at arm time; they last for the editor session): AS62_ONLY (phase-name prefixes; settle /
# spawn2 / board always run; s_empty expects to follow s_gunner), AS62_SCHEME (3), AS62_COUNT (5), AS62_COUNT_D (8),
# AS62_D_HEALTH (0.5), AS62_STATION (4 = turret L), AS62_HOLD ((2900, -395, 1001)), AS62_HOLD_S (4.0), AS62_HOLD_HITS
# (2; 0 = no holds), AS62_JUMP_CM (2000, 0 = off), AS62_JUMP_S (4.0), AS62_MIN_HP (30), AS62_TOPUP_HP (55; 0 = off: inside
# s_pilot / s_gunner / s_turret the player is topped up below it and the amount is added back to the phase's loss, so a
# phase is not cut short by the safety), AS62_CAPS (True).
# Not here: T2.8 (own-crew splash immunity) needs damage dummies on the deck: only GAS characters with their own ASC have
# health to measure; the project has no enemy Blueprint (AMyEnemyChar is C++ only, its attributes come from a BP class
# info), and BP_MyCharMech without a PlayerState has no ASC. Listen-server swarm cases (a gunner on a DRIVEN ship) are
# as_60 territory.
import json, math, os, time, traceback  # unreal = inbox namespace

AS62_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as62_src = open(AS62_AS30).read()
exec(compile(_as62_src[:_as62_src.index('\nclass AsRun')], AS62_AS30, 'exec'), globals())   # OUT, MAP_NAME, SHIP_CLS, DMG_GE, v3, r, dist, wrap180, tl_get/tl_set, gp, valid, find_log

AS62_VERSION = 'as_62_pie_swarm 2026-11-27, s_cannon'
SWDIR = os.path.join(OUT, 'round2_swarm')
CAPS62 = os.path.join(OUT, 'captures', 'round2_swarm')
TEMP62 = 'TEMP_AS62_'
SETTINGS_CLS62 = '/Script/Aura.AirshipSettings'
SPAWNER_CLS62 = '/Script/Aura.MechSentinelWaveSpawner'
CONFIG62 = '/Game/MechSentinel/Data/DA_MechSentinelConfig'
POTION62 = '/Game/Level/GAS/GameplayEffects/GE_HealthPotion.GE_HealthPotion_C'
BALL_BP62 = '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C'
BALL_SPEED62, BALL_GRAVITY62 = 7000.0, 0.6     # the cannon's launch speed and the ball's gravity scale (as_59 T2.1)
FIXED_FPS62 = 30.0
MAX_CAPS62 = 10
# L_AirshipTest (as_22_test_map.py): start platform 100 x 100 m at the origin (top z 0, PlayerStart (-2500, -2500)), cannon
# walls at x -3000..3000, obstacles only at x >= 35 km, ground top z -19950. P1 is open air 280 m west of the platform.
P1 = (-30000.0, 2500.0, 1600.0)                  # ship 1's test spot (bow +X)
P2 = (P1[0], P1[1] + 5000.0, P1[2])              # ship 2 (undriven, unmanned) 50 m to starboard of it
PARK2 = (0.0, 40000.0, 1600.0)                   # ship 2 out of the way (s_turret: TurretFire drives every ship's turrets)
SP_A = (P1[0], P1[1] - 5500.0, P1[2] + 400.0)    # wave 1: 55 m to port of P1 (away from ship 2), 4 m up
SP_D = (P1[0] + 5500.0, P1[1], P1[2] + 900.0)    # wave 2: 55 m ahead of ship 1's root (24 m past the bow tip), 9 m up
SPAWNER_LOC = (P1[0], P1[1], P1[2] + 4000.0)
CHAR_FOOT = (-2500.0, -2500.0, 150.0)            # the PlayerStart area on the start platform
SNAP_R = 300000.0                                # the sentinel query capsule (every sentinel of the map)
HOLD_DEFAULT = (2900.0, -395.0, 1001.0)
MOUNTS_DEFAULT = [{'loc': [2100.0, -245.0, 655.0], 'ymin': -110.0, 'ymax': 30.0, 'pmin': -20.0, 'pmax': 40.0},
                  {'loc': [2100.0, 245.0, 655.0], 'ymin': -30.0, 'ymax': 110.0, 'pmin': -20.0, 'pmax': 40.0}]
HITBOX_Z, HITBOX_EXT = 95.0, (60.0, 60.0, 95.0)  # AAirshipTurret: HitBox at (0, 0, 95), extent (60, 60, 95)
SCHEME_NAMES62 = {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}
SKIPPED62 = {'T2.8': 'as_59 T2.8_own_crew_splash_S (a deck rider, then the gunner of L1, inside the splash of ship 1\'s own ball)',
             'SW.b_driven': 'a gunner on a DRIVEN ship needs a second player (listen server, as_60 territory)'}
TAGGED_PAT = 'Sentinel bullet hit tagged target '


def en(x):
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


def same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def parse_export(txt):
    """'(A=1.0,B=(0.1,0.2),C=True)' -> dict; nested parentheses become lists of floats (or strings). As as_59's."""
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
    args = kw.get('args', ())
    for n in names:
        f = getattr(obj, n, None)
        if f is not None:
            return f(*args)
    raise AttributeError('none of %s on %s' % (names, obj))


HIT_INFO_ERR62 = []


def hit_info(res):
    """(blocking, impact point list, actor, component) of a line trace result (HitResult, tuple or None): HitResult.to_tuple()
    (UE 5.8 Python has no GameplayStatics.break_hit_result), else its properties; failures recorded once (as_59)."""
    if res is None:
        return False, None, None, None
    hit = res
    if isinstance(res, tuple):
        hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
        if hit is None:
            return False, None, None, None
    t = None
    for how in ('to_tuple', 'break'):
        try:
            t = tuple(hit.to_tuple()) if how == 'to_tuple' else tuple(unreal.GameplayStatics.break_hit_result(hit))
            break
        except Exception:  # noqa: BLE001
            if len(HIT_INFO_ERR62) < 4:
                HIT_INFO_ERR62.append('%s: %s' % (how, traceback.format_exc().strip().splitlines()[-1]))
    if t is not None:
        bools = [x for x in t if isinstance(x, bool)]
        nums = [x for x in t if isinstance(x, float)]
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
        if len(HIT_INFO_ERR62) < 4:
            HIT_INFO_ERR62.append('props: %s' % traceback.format_exc().strip().splitlines()[-1])
        return False, None, None, None


def out_list(res):
    """the out array of a call that returns (int, array) (FindSentinelsInCapsule), or the array itself."""
    if res is None or isinstance(res, (bool, int, float)):
        return []
    if isinstance(res, tuple):
        for x in res:
            if x is None or isinstance(x, (bool, int, float, str)):
                continue
            try:
                return list(x)
            except TypeError:
                continue
        return []
    try:
        return list(res)
    except TypeError:
        return []


def out_struct(res):
    """the out struct of a bool function with an out param (GetSentinelInfo): None when false (UE Python returns None, the
    struct, or a tuple with the bool)."""
    if res is None or isinstance(res, bool):
        return None
    if isinstance(res, tuple):
        if any(x is False for x in res):
            return None
        return next((x for x in res if x is not None and not isinstance(x, (bool, int, float, str))), None)
    return res


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def median(xs):
    s = sorted(xs)
    if not s:
        return None
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def num_in(txt, name, default):
    """a number after Name= / "Name": in a ToolsetLibrary JSON / export text (the trait's Parameters), else default."""
    import re
    m = re.search(r'"?%s"?\s*[:=]\s*"?(-?[0-9.]+)' % name, txt or '')
    try:
        return float(m.group(1)) if m else default
    except ValueError:
        return default


class SwarmRun(object):
    def __init__(self):
        self.R = {'version': AS62_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': {},
                  'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'kills': [], 'damage_events': {},
                  'holds': [], 'tagged': {}, 'done': False, 'setup': {}}
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
        self.last_series = -1.0
        self.last_write = 0.0
        self.last_tail = -1.0
        self.D = {}
        self.w = self.pc = self.char = self.ship = self.ship2 = self.spawner = self.swarm = None
        self.cap = None
        self.cap_dead = False
        self.ncap = 0
        self.log_file = find_log()
        self.log_off = os.path.getsize(self.log_file) if self.log_file else 0
        self.log_pos = self.log_off
        self.log_rest = ''
        self.log_counts = {}
        self.log_samples = {}
        self.user_play = False
        self.frames = 0
        self.local = {}
        self.cmds_run = []
        self.snapv = []
        self.snap_t = -1.0
        self.bound = []
        self.mounts = [dict(m) for m in MOUNTS_DEFAULT]
        self.pivot_h = 150.0
        self.params = {'attack_range': 2500.0, 'exit_scale': 1.25, 'orbit_radius': 1500.0, 'target_h': 90.0}
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
            with open(os.path.join(SWDIR, 'sw_log.txt'), 'a') as f:
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
        return 'as_62 phase %s (%d/%d) game_t %.1f wall %.0f s frames %d alive %s checks %s, about %s game s left, done %s' % (
            self.phase, self.pi + 1, len(self.phases), self.now, time.time() - self.wall0, self.frames, len(self.snapv), c,
            None if left is None else int(left), self.R['done'])

    def write(self, force=False):
        if not force and time.time() - self.last_write < 2.0:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        self.R['tagged'] = self.log_counts
        try:
            with open(os.path.join(SWDIR, 'sw_result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
            with open(os.path.join(SWDIR, 'sw_status.txt'), 'w') as f:
                f.write(self.status_text() + '\n')
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- arm / restore
    def settings(self):
        return unreal.get_default_object(unreal.load_class(None, SETTINGS_CLS62))

    def build_phases(self):
        ph = [('settle', 3.0), ('spawn2', 3.0), ('board', 2.5), ('s_pilot', 30.0), ('s_gunner', 25.0), ('s_empty', 22.0),
              ('s_turret', 45.0), ('s_cannon', 33.0)]
        only = self.cfg.get('only')
        if only:
            keep = set(['settle', 'spawn2', 'board'] + list(only))
            ph = [p for p in ph if p[0] in keep or any(p[0].startswith(o) for o in only)]
        return ph

    def make_wave(self, count, health):
        w = unreal.MechSentinelWave()
        for k, v in (('count', int(count)), ('delay_before', 0.3), ('spawn_duration', 1.0), ('time_limit', 0.0),
                     ('health_multiplier', float(health)), ('armor_multiplier', 1.0), ('damage_multiplier', 1.0),
                     ('attack_speed_multiplier', 1.0), ('move_speed_multiplier', 1.0), ('self_buff_chance_multiplier', 1.0)):
            w.set_editor_property(k, v)
        return w

    def arm(self):
        os.makedirs(SWDIR, exist_ok=True)
        os.makedirs(CAPS62, exist_ok=True)
        g = globals()
        hold = g.get('AS62_HOLD') or HOLD_DEFAULT
        self.cfg = {'scheme': int(g.get('AS62_SCHEME', 3) or 0), 'only': tuple(g.get('AS62_ONLY') or ()),
                    'count': max(1, int(g.get('AS62_COUNT', 5) or 5)), 'count_d': max(1, int(g.get('AS62_COUNT_D', 8) or 8)),
                    'd_health': max(0.05, float(g.get('AS62_D_HEALTH', 0.5) or 0.5)), 'station': int(g.get('AS62_STATION', 4)),
                    'hold': [float(x) for x in hold], 'hold_s': float(g.get('AS62_HOLD_S', 4.0) or 4.0),
                    'hold_hits': max(0, int(2 if g.get('AS62_HOLD_HITS') is None else g.get('AS62_HOLD_HITS'))),   # 0 = no holds
                    'min_hp': float(g.get('AS62_MIN_HP', 30.0) or 30.0),
                    'topup_hp': float(55.0 if g.get('AS62_TOPUP_HP') is None else g.get('AS62_TOPUP_HP')),   # 0 = no top-ups inside a phase
                    'jump_cm': float(g.get('AS62_JUMP_CM', 2000.0) or 0.0), 'jump_s': max(1.0, float(g.get('AS62_JUMP_S', 4.0) or 4.0)),
                    'caps': bool(g.get('AS62_CAPS', True))}
        self.phases = self.build_phases()
        self.R['cfg'] = self.cfg
        self.R['phases'] = self.phases
        with open(os.path.join(SWDIR, 'sw_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (AS62_VERSION, self.R['armed_utc'], self.cfg))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open the map first' % (ew.get_path_name(), MAP_NAME))
            return False
        for cls in ('/Script/Aura.AirshipTurret', SPAWNER_CLS62, '/Script/Aura.MechSentinelCombatLibrary'):
            if unreal.load_class(None, cls) is None:
                self.line('FAIL', '%s not found: the round-2 C++ / the swarm is not built into this editor' % cls)
                return False
        config = unreal.load_asset(CONFIG62)
        if config is None:
            self.line('FAIL', '%s not found (git lfs pull?)' % CONFIG62)
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 4 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        self.read_config(config)
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS62})
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
                'CrewDamageShare', 'TurretGunDamageMultiplier', 'DriverTurretArcDeg', 'bHoldWhenUnpiloted', 'bSpawnTurrets'))
            self.R['setup']['settings'] = dict((k, str(v)) for k, v in self.orig['settings'].items())
            ms = []
            for m in st.get_editor_property('TurretMounts') or []:
                ms.append({'loc': v3(m.get_editor_property('location')), 'ymin': float(m.get_editor_property('yaw_min_deg')),
                           'ymax': float(m.get_editor_property('yaw_max_deg')), 'pmin': float(m.get_editor_property('pitch_min_deg')),
                           'pmax': float(m.get_editor_property('pitch_max_deg'))})
            if len(ms) >= 2:
                self.mounts = ms[:2]
            self.R['setup']['turret_mounts'] = self.mounts
        except Exception:  # noqa: BLE001
            self.err('settings_snapshot')
        self.share = float((self.orig.get('settings') or {}).get('CrewDamageShare', 0.25))
        self.aim_chance = None
        try:
            self.aim_chance = float(self.settings().get_editor_property('SwarmTurretAimChance'))
        except Exception:  # noqa: BLE001
            pass                                     # a build before 2026-11-27: every bullet aims at the root
        self.R['setup']['SwarmTurretAimChance'] = self.aim_chance
        try:
            unreal.SystemLibrary.execute_console_command(None, 'log LogMechSentinel Verbose')
            self.orig['log_verbose'] = True
        except Exception:  # noqa: BLE001
            self.err('log_verbose')
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP62):
                    eas.destroy_actor(a)
            sp = eas.spawn_actor_from_class(unreal.load_class(None, SPAWNER_CLS62), unreal.Vector(*SPAWNER_LOC))
            sp.set_actor_label(TEMP62 + 'Spawner')
            for k, v in (('entity_config', config), ('advance_mode', unreal.MechSentinelWaveAdvance.WHEN_CLEARED), ('auto_start', False),
                         ('repeat_last_wave', False), ('use_wave_curves', False), ('bind_to_path_spawners', False),
                         ('spawner_is_fallback_target', False), ('count_multiplier', 1.0),
                         ('max_alive', max(self.cfg['count'], self.cfg['count_d']) + 4), ('spawn_batch_size', 25),
                         ('corner_spawn_extent', unreal.Vector(600.0, 600.0, 250.0)),
                         ('waves', [self.make_wave(self.cfg['count'], 1.0), self.make_wave(self.cfg['count_d'], self.cfg['d_health'])])):
                sp.set_editor_property(k, v)
            self.R['setup']['spawner'] = {'label': sp.get_actor_label(), 'config': config.get_path_name(),
                                          'waves': [(self.cfg['count'], 1.0), (self.cfg['count_d'], self.cfg['d_health'])]}
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(P1[0], P1[1] - 6000.0, P1[2] + 2000.0))
            cap.set_actor_label(TEMP62 + 'Capture')
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
            self.line('INFO', 'placed %sSpawner (%s, waves %s) + %sCapture in the editor level (removed after PIE, the map is not saved)' % (
                TEMP62, CONFIG62, self.R['setup']['spawner']['waves'], TEMP62))
        except Exception:  # noqa: BLE001
            self.err('temp_actors')
            self.line('FAIL', 'could not place the TEMP spawner: not armed')
            self.restore()
            self.remove_temp()
            return False
        with open(os.path.join(SWDIR, 'sw_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed; standalone PIE requested; %d phases, about %d game s' % (len(self.phases), sum(d for _, d in self.phases)))
        return True

    def read_config(self, config):
        """the sentinel trait's numbers the checks use (attack range, exit scale, orbit radius, target height offset)."""
        try:
            traits = config.get_editor_property('config').get_editor_property('traits')
            tr = next((t for t in traits if t is not None and 'MechSentinelTrait' in t.get_class().get_name()), None)
            if tr is None:
                self.line('WARN', 'no MechSentinelTrait in %s: default parameters assumed' % CONFIG62)
                return
            txt = unreal.ToolsetLibrary.get_object_properties(tr, ['Parameters', 'Attributes', 'MovementSpeed', 'SwarmGroup'])
            self.R['setup']['trait'] = txt[:3000]
            self.params = {'attack_range': num_in(txt, 'AttackRange', 2500.0), 'exit_scale': num_in(txt, 'AttackExitRangeScale', 1.25),
                           'orbit_radius': num_in(txt, 'OrbitRadius', 1500.0), 'target_h': num_in(txt, 'TargetHeightOffset', 90.0),
                           'attack_damage': num_in(txt, 'AttackDamage', 3.0), 'attack_speed': num_in(txt, 'AttackSpeed', 0.6),
                           'max_health': num_in(txt, 'MaxHealth', 120.0), 'move_speed': num_in(txt, 'MovementSpeed', 900.0)}
        except Exception:  # noqa: BLE001
            self.err('read_config')
        self.R['setup']['params'] = self.params

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
            st = self.settings()
            for n, v in (self.orig.get('settings') or {}).items():
                st.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_settings')
        try:
            if self.orig.get('log_verbose'):
                unreal.SystemLibrary.execute_console_command(None, 'log LogMechSentinel Log')
                self.orig['log_verbose'] = False
        except Exception:  # noqa: BLE001
            self.err('restore_log')

    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            n = 0
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP62):
                    eas.destroy_actor(a)
                    n += 1
            self.line('INFO', 'removed %d %s* actors from the editor level' % (n, TEMP62))
        except Exception:  # noqa: BLE001
            self.err('remove_temp')

    def unbind(self):
        for dlg, fn in self.bound:
            try:
                dlg.remove_callable(fn)
            except Exception:  # noqa: BLE001
                pass
        self.bound = []

    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        try:
            if self.w is not None and self.local.get('turret_fire_on'):
                unreal.SystemLibrary.execute_console_command(self.w, 'Aura.Airship.TurretFire 0')
                self.local['turret_fire_on'] = False
        except Exception:  # noqa: BLE001
            pass
        for s in (self.ship, self.ship2):
            try:
                if valid(s):
                    s.debug_clear_input()
            except Exception:  # noqa: BLE001
                pass
        self.unbind()
        self.log_tail(final=True)
        self.scan_log()
        for k, why in SKIPPED62.items():
            if k not in self.R['checks']:
                self.R['checks'][k] = {'status': 'SKIP', 'summary': why, 'data': None, 't': r(self.now), 'phase': '-'}
        self.R['hit_info_err'] = list(HIT_INFO_ERR62)
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
        write_sw_report(self.R)
        self.line('INFO', 'done; results in round2_swarm/sw_result.json / sw_report.txt')

    # ---------------------------------------------------------------- log
    def log_tail(self, final=False):
        """new log text since the last call: tagged-hit lines per phase and target, problems, the user's own Play."""
        if not self.log_file:
            return
        if not final and self.now - self.last_tail < 0.5:
            return
        self.last_tail = self.now
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_pos)
                txt = f.read()
                self.log_pos = f.tell()
        except Exception:  # noqa: BLE001
            return
        txt = self.log_rest + txt
        lines = txt.split('\n')
        self.log_rest = lines.pop() if not final else ''
        ph = self.phase
        for l in lines:
            if TAGGED_PAT in l:
                try:
                    rest = l.split(TAGGED_PAT, 1)[1]
                    name = rest.split(' ', 1)[0]
                    dmg = float(rest.split('(', 1)[1].split(')', 1)[0])
                except Exception:  # noqa: BLE001
                    name, dmg = '?', 0.0
                c = self.log_counts.setdefault(ph, {}).setdefault(name, [0, 0.0])
                c[0] += 1
                c[1] = round(c[1] + dmg, 2)
            for k, p in (('ensure', 'Ensure condition failed'), ('assert', 'Assertion failed'), ('accessed_none', 'Accessed None'),
                         ('sentinel_warn', 'LogMechSentinel: Warning'), ('sentinel_err', 'LogMechSentinel: Error'),
                         ('mass_err', 'LogMass: Error'), ('airship_warn', 'LogAirship: Warning'), ('error', 'Error:'),
                         ('not_recognized', 'Command not recognized'), ('user_play', 'Repeating last play command'),
                         ('crew', 'crew damage')):
                if p in l:
                    s = self.log_samples.setdefault(k, {'count': 0, 'sample': []})
                    s['count'] += 1
                    if len(s['sample']) < 8:
                        s['sample'].append(l.strip()[:300])
                    if k == 'user_play':
                        self.user_play = True

    def scan_log(self):
        self.R['log_scan'] = self.log_samples
        bad = dict((k, v['count']) for k, v in self.log_samples.items() if k in ('ensure', 'assert', 'accessed_none', 'sentinel_err', 'mass_err'))
        warn = dict((k, v['count']) for k, v in self.log_samples.items() if k in ('sentinel_warn', 'not_recognized'))
        st = 'FAIL' if any(bad.values()) else ('WARN' if any(warn.values()) else 'PASS')
        self.check('SW.log', st, 'editor log during the run: %s (want no ensure / assert / Accessed None / LogMechSentinel or LogMass '
                   'error); warnings %s; tagged-hit lines per phase %s' % (bad, warn, self.log_counts),
                   {'samples': dict((k, v['sample']) for k, v in self.log_samples.items())})

    def tagged(self, ph, name=None):
        """(lines, damage) of the tagged path in phase ph: for one target name, or all."""
        d = self.log_counts.get(ph) or {}
        if name is not None:
            c = d.get(name) or [0, 0.0]
            return c[0], c[1]
        return sum(c[0] for c in d.values()), round(sum(c[1] for c in d.values()), 2)

    # ---------------------------------------------------------------- PIE helpers
    def cmd(self, c, quiet=False):
        unreal.SystemLibrary.execute_console_command(self.w, c)
        self.cmds_run.append(c)
        if not quiet:
            self.event('cmd', cmd=c)
            self.line('INFO', 'console: %s' % c)

    def tele(self, ship):
        try:
            return parse_export(ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def ship_hp(self, ship):
        if not valid(ship):
            return None
        v = self.tele(ship).get('Health')
        return round(float(v), 3) if isinstance(v, float) else None

    def health(self, a, attr='Health'):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None
            x = asc.get_gameplay_attribute_value(self.attrs[attr])
            return round(float(x[0] if isinstance(x, tuple) else x), 3)
        except Exception:  # noqa: BLE001
            self.err('health')
            return None

    def heal_if_low(self, frac=0.7):
        """tops the player up with GE_HealthPotion (instant only) when below frac of MaxHealth; at most 8 applications."""
        try:
            c = self.char if valid(self.char) else None
            if c is None:
                return
            h, mx = self.health(c), self.health(c, 'MaxHealth')
            if h is None or not mx or h >= frac * mx:
                return
            cls = unreal.load_class(None, POTION62)
            if h <= 0.0:
                return 0.0                           # dead: a potion is no revive
            pol = en(unreal.get_default_object(cls).get_editor_property('duration_policy')) if cls else None
            if pol != 'INSTANT':
                self.line('WARN', 'GE_HealthPotion is %s (not instant): no top-up, health %s / %s' % (pol, h, mx))
                return
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(c)
            h0 = h
            for _ in range(8):
                spec = asc.make_outgoing_spec(cls, 1.0, asc.make_effect_context())
                asc.apply_gameplay_effect_spec_to_self(spec)
                h1 = self.health(c)
                if h1 is None or h1 >= 0.95 * mx or h1 <= h + 0.01:
                    h = h1
                    break
                h = h1
            self.event('heal', before=h0, after=h, max=mx)
            self.line('INFO', 'player topped up with GE_HealthPotion: %s -> %s (max %s)' % (h0, h, mx))
            return max(0.0, (h or h0) - h0)
        except Exception:  # noqa: BLE001
            self.err('heal')
        return 0.0

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
                fc.set_editor_property(n, 0.0, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('wind_off')

    def set_scheme(self, ship, s):
        try:
            ship.set_control_scheme(getattr(unreal.AirshipControlScheme, SCHEME_NAMES62[int(s)]))
        except Exception:  # noqa: BLE001
            self.err('set_scheme')

    def pawn(self):
        try:
            return self.pc.get_controlled_pawn()
        except Exception:  # noqa: BLE001
            return None

    def ps_pawn(self):
        """the PlayerState's pawn: what UMechSentinelSwarmSubsystem::GatherPlayerTargets hands the swarm."""
        try:
            ps = self.pc.get_editor_property('player_state')
            if ps is None:
                return None
            try:
                return ps.get_pawn()
            except Exception:  # noqa: BLE001
                return gp(ps, 'pawn_private', 'PawnPrivate')
        except Exception:  # noqa: BLE001
            self.err('ps_pawn')
            return None

    def tp_char(self, loc, yaw=0.0):
        try:
            if valid(self.char) and self.char.get_attach_parent_actor() is None:
                self.char.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
                cm = gp(self.char, 'character_movement', 'CharacterMovement')
                if cm:
                    cm.stop_movement_immediately()
                return True
        except Exception:  # noqa: BLE001
            self.err('tp_char')
        return False

    def turrets(self, ship):
        try:
            return [t for t in (ship.get_editor_property('Turrets') or []) if valid(t)]
        except Exception:  # noqa: BLE001
            self.err('turrets')
            return []

    def turret(self, ship, i):
        return next((t for t in self.turrets(ship) if call(t, 'get_turret_index') == i), None)

    def thp(self, ship):
        """[health of turret 0, turret 1] (None for a missing one)."""
        out = [None, None]
        for t in self.turrets(ship):
            try:
                i = call(t, 'get_turret_index')
                if i in (0, 1):
                    out[i] = round(float(call(t, 'get_health')), 3)
            except Exception:  # noqa: BLE001
                self.err('thp')
        return out

    def tshots(self, ship):
        n = 0
        for t in self.turrets(ship):
            try:
                n += int(call(t, 'get_shot_count'))
            except Exception:  # noqa: BLE001
                pass
        return n

    def gunner(self, ship, s):
        try:
            return call(ship, 'get_station_gunner', args=(s,))
        except Exception:  # noqa: BLE001
            try:
                return (ship.get_editor_property('StationGunners') or [None] * 6)[s]
            except Exception:  # noqa: BLE001
                return None

    def hull_local(self, ship, p):
        return v3(unreal.MathLibrary.inverse_transform_location(ship.get_actor_transform(), unreal.Vector(*p)))

    def world_of(self, ship, local):
        return v3(unreal.MathLibrary.transform_location(ship.get_actor_transform(), unreal.Vector(*local)))

    def target_point(self, actor):
        """where the swarm aims at that pawn: its location + the trait's TargetHeightOffset."""
        p = v3(actor.get_actor_location())
        return [p[0], p[1], p[2] + self.params['target_h']]

    def exit_range(self):
        return self.params['attack_range'] * self.params['exit_scale']

    def trace(self, a, b, ignore=None):
        try:
            res = unreal.SystemLibrary.line_trace_single(self.w, unreal.Vector(*a), unreal.Vector(*b), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                                                         False, ignore or [], unreal.DrawDebugTrace.NONE, True)
            ok, imp, act, comp = hit_info(res)
            return {'hit': ok, 'at': r(imp, 1) if imp else None, 'actor': act.get_name() if act else None,
                    'comp': comp.get_name() if comp else None, 'dist': r(dist(a, imp), 1) if imp else None}
        except Exception:  # noqa: BLE001
            self.err('trace')
            return None

    def comp_hit(self, comp, a, b):
        """does the segment a-b cross the component's collision (LineTraceComponent)?"""
        try:
            res = comp.line_trace_component(unreal.Vector(*a), unreal.Vector(*b), False, False, False)
            if res is None or res is False:
                return False
            if isinstance(res, tuple):
                if res and isinstance(res[0], bool):
                    return res[0]
                return any(isinstance(x, unreal.Vector) for x in res)
            return bool(res)
        except Exception:  # noqa: BLE001
            self.err('comp_hit')
            return None

    # ---------------------------------------------------------------- the swarm
    def find_swarm(self):
        try:
            sps = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, SPAWNER_CLS62))
            self.spawner = next((s for s in sps if TEMP62 in s.get_actor_label()), sps[0] if sps else None)
        except Exception:  # noqa: BLE001
            self.err('find_spawner')
        try:
            self.swarm = unreal.SubsystemBlueprintLibrary.get_world_subsystem(self.w, unreal.MechSentinelSwarmSubsystem)
        except Exception:  # noqa: BLE001
            self.swarm = None
        if self.swarm is None:
            try:
                self.swarm = next((s for s in unreal.ObjectIterator(unreal.MechSentinelSwarmSubsystem) if same(s.get_outer(), self.w)), None)
            except Exception:  # noqa: BLE001
                self.err('find_swarm')
        return self.spawner is not None and self.swarm is not None

    def bind(self):
        for prop, fn in (('on_sentinel_killed', self.on_killed), ('on_sentinel_damaged', self.on_damaged)):
            try:
                dlg = getattr(self.swarm, prop, None)
                if dlg is None:
                    dlg = self.swarm.get_editor_property(prop)
                dlg.add_callable(fn)
                self.bound.append((dlg, fn))
            except Exception:  # noqa: BLE001
                self.err('bind_' + prop)
        self.R['setup']['delegates_bound'] = len(self.bound)

    @staticmethod
    def hkey(h):
        try:
            return '%s:%s' % (gp(h, 'index'), gp(h, 'serial_number'))
        except Exception:  # noqa: BLE001
            return '?'

    def on_killed(self, sentinel, location, instigator):
        try:
            self.R['kills'].append({'t': r(self.now), 'ph': self.phase, 'k': self.hkey(sentinel), 'loc': r(v3(location), 0),
                                    'by': instigator.get_name() if instigator is not None else None,
                                    'win': self.D.get('win')})
        except Exception:  # noqa: BLE001
            pass

    def on_damaged(self, sentinel, damage, location, instigator):
        try:
            k = '%s|%s|%s' % (self.phase, self.D.get('win'), instigator.get_name() if instigator is not None else None)
            d = self.R['damage_events'].setdefault(k, [0, 0.0])
            d[0] += 1
            d[1] = round(d[1] + float(damage), 2)
            if self.phase == 's_cannon':        # every event of the cannonball phase, one by one
                self.D.setdefault('dmg', []).append((r(self.now - self.p_t0, 3), self.D.get('win'), self.hkey(sentinel), round(float(damage), 3),
                                                     instigator.get_name() if instigator is not None else None))
        except Exception:  # noqa: BLE001
            pass

    def snap(self, force=False):
        """alive sentinels (server truth, not dead): [{'k', 'h', 'loc', 'st', 'hp', 'max'}], cached per frame."""
        if not force and self.snap_t == self.now:
            return self.snapv
        out = []
        try:
            lib = unreal.MechSentinelCombatLibrary
            hits = out_list(lib.find_sentinels_in_capsule(self.w, unreal.Vector(*P1), unreal.Rotator(0.0, 0.0, 0.0), SNAP_R, SNAP_R))
            for h in hits:
                hd = gp(h, 'sentinel')
                info = out_struct(lib.get_sentinel_info(self.w, hd))
                if info is None:
                    continue
                st = en(gp(info, 'state'))
                if st == 'DEAD':
                    continue
                out.append({'k': self.hkey(hd), 'h': hd, 'loc': v3(gp(info, 'location')), 'st': st,
                            'hp': round(float(gp(info, 'health')), 2), 'max': round(float(gp(info, 'max_health')), 2)})
        except Exception:  # noqa: BLE001
            self.err('snap')
        self.snapv, self.snap_t = out, self.now
        return out

    def sentinel_loc(self, hd):
        try:
            info = out_struct(unreal.MechSentinelCombatLibrary.get_sentinel_info(self.w, hd))
            if info is None:
                return None, None
            return v3(gp(info, 'location')), en(gp(info, 'state'))
        except Exception:  # noqa: BLE001
            self.err('sentinel_loc')
            return None, None

    def start_wave(self, point, wave):
        try:
            n = self.spawner.start_wave_at_points([unreal.Vector(*point)], int(wave), None)
            self.event('wave', point=r(list(point), 0), wave=wave, number=n)
            self.line('INFO', 'StartWaveAtPoints(%s, wave %d) -> %s' % (r(list(point), 0), wave, n))
            return n
        except Exception:  # noqa: BLE001
            self.err('start_wave')
            return 0

    def despawn(self, why):
        try:
            self.spawner.despawn_all(False)
            self.event('despawn', why=why, alive=len(self.snapv))
            self.line('INFO', 'DespawnAll(false): %s (%d alive)' % (why, len(self.snapv)))
        except Exception:  # noqa: BLE001
            self.err('despawn')

    def stats(self, pts, ref):
        """distances (cm) of the sentinels to a point."""
        return [dist(p['loc'], ref) for p in pts]

    def in_arc(self, ship, loc, ti, margin=2.0):
        """the point inside turret ti's yaw / pitch limits seen from its pivot (hull space, as AAirshipTurret::IsAimInArc)."""
        m = self.mounts[ti]
        l = self.hull_local(ship, loc)
        dx, dy, dz = l[0] - m['loc'][0], l[1] - m['loc'][1], l[2] - (m['loc'][2] + self.pivot_h)
        yaw = math.degrees(math.atan2(dy, dx))
        pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
        rng = math.sqrt(dx * dx + dy * dy + dz * dz)
        return m['ymin'] + margin <= yaw <= m['ymax'] - margin and m['pmin'] + margin <= pitch <= m['pmax'] - margin and rng <= 20000.0

    # ---------------------------------------------------------------- captures
    def capture(self, label, kind, ship=None):
        if not self.cfg.get('caps') or self.cap_dead or self.ncap >= MAX_CAPS62:
            return None
        try:
            if self.cap is None:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.SceneCapture2D)
                        if (TEMP62 + 'Capture') in a.get_actor_label()]
                if not caps:
                    self.cap_dead = True
                    self.line('WARN', 'no %sCapture in the PIE world: no captures' % TEMP62)
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
                views = {'side': ((0.0, -5200.0, 1800.0), (300.0, 0.0, 500.0)),
                         'gunner': ((2600.0, -4200.0, 1600.0), (2000.0, -245.0, 800.0)),
                         'bow': ((6500.0, -2600.0, 1600.0), (2100.0, 0.0, 800.0)),
                         'hold': ((3600.0, -2400.0, 1300.0), (2500.0, -300.0, 900.0))}
                if kind not in views:
                    return None
                frm, to = at(*views[kind][0]), at(*views[kind][1])
                rot = unreal.MathLibrary.find_look_at_rotation(frm, to)
                fov = 65.0
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(frm, rot, False, True)
            cc.capture_scene()
            name = '%s_%s' % (label, kind)
            unreal.RenderingLibrary.export_render_target(self.w, rt, CAPS62, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 't': r(self.now), 'file': os.path.join(CAPS62, name + '.png')})
            return name
        except Exception:  # noqa: BLE001
            self.err('capture')
            self.cap_dead = True
            return None

    # ---------------------------------------------------------------- sampling
    def sample(self):
        """10 Hz: the swarm snapshot and the health of everything; per phase accumulators; 5 Hz series; the safety cut."""
        if self.now - self.last_sample < 0.099:
            return
        self.last_sample = self.now
        try:
            pts = self.snap(force=True)
            acc = self.D.setdefault('acc', {'n': 0, 'alive': [], 'att': [], 'att_s': 0.0, 'ahead_s': 0.0, 'first_att': None,
                                            'min_d2': None, 'ps': {}})
            acc['n'] += 1
            natt = len([p for p in pts if p['st'] == 'ATTACKING'])
            acc['alive'].append(len(pts))
            acc['att'].append(natt)
            acc['att_s'] += 0.1 * natt
            if natt and acc['first_att'] is None:
                acc['first_att'] = r(self.now - self.p_t0, 2)
            psp = self.ps_pawn()
            pk = psp.get_name() if psp is not None else None
            acc['ps'][pk] = acc['ps'].get(pk, 0) + 1
            s = {'t': r(self.now, 2), 'ph': self.phase, 'n': len(pts), 'att': natt}
            if valid(self.ship):
                q1 = self.target_point(self.ship)
                d1 = self.stats(pts, q1)
                s['S1'] = {'hp': self.ship_hp(self.ship), 't': self.thp(self.ship), 'loc': r(v3(self.ship.get_actor_location()), 0)}
                s['d1'] = r(median(d1), 0) if d1 else None
                # sentinels ahead of the turret line (hull x > mount x) and inside the attack exit range of the ship's target
                ahead = 0
                for p in pts:
                    if p['st'] == 'ATTACKING' and dist(p['loc'], q1) <= self.exit_range() and self.hull_local(self.ship, p['loc'])[0] > self.mounts[0]['loc'][0]:
                        ahead += 1
                acc['ahead_s'] += 0.1 * ahead
                s['ahead'] = ahead
            if valid(self.ship2):
                d2 = self.stats(pts, v3(self.ship2.get_actor_location()))
                s['S2'] = {'hp': self.ship_hp(self.ship2)}
                if d2:
                    s['d2'] = r(min(d2), 0)
                    acc['min_d2'] = s['d2'] if acc['min_d2'] is None else min(acc['min_d2'], s['d2'])
            if valid(self.char):
                s['C'] = {'hp': self.health(self.char), 'att': self.char.get_attach_parent_actor().get_name() if self.char.get_attach_parent_actor() else None}
                dc = self.stats(pts, self.target_point(self.char))
                s['dc'] = r(median(dc), 0) if dc else None
            s['ps'] = pk
            if self.now - self.last_series >= 0.199:
                self.last_series = self.now
                if self.now - self.local.get('pts_t', -9.0) >= 0.99:
                    self.local['pts_t'] = self.now
                    s['pts'] = [[p['k'], p['st'][:3]] + r(p['loc'], 0) + [p['hp']] for p in pts]
                self.R['series'].append(s)
            # safety: never lose the player to the swarm (the phase's checks say so)
            hp = (s.get('C') or {}).get('hp')
            # a top-up inside a phase (2026-11-27: 5 sentinels take a turret gunner from 104 to 30 in 14 s, and the crew
            # share does the same to the pilot of a ship that lost 300): the amount is added back to the phase's loss
            # (D['healed'], zeroed when the phase takes its baseline), so the checks still measure every point lost
            if hp is not None and 0.0 < hp < self.cfg['topup_hp'] and self.phase in ('s_pilot', 's_gunner', 's_turret'):
                got = self.heal_if_low(0.95) or 0.0
                if got > 0.0:
                    self.D['healed'] = round(self.D.get('healed', 0.0) + got, 3)
                    self.D.setdefault('topups', []).append([r(self.now - self.p_t0, 2), hp, r(hp + got, 3)])
                    hp = hp + got
            if hp is not None and 0.0 < hp < self.cfg['min_hp'] and pts and not self.D.get('safety'):
                self.D['safety'] = r(self.now - self.p_t0, 2)
                self.line('WARN', 'player health %s < AS62_MIN_HP %s: the swarm is removed for the rest of the phase' % (hp, self.cfg['min_hp']))
                self.despawn('safety (player health %s)' % hp)
        except Exception:  # noqa: BLE001
            self.err('sample')

    def acc_summary(self):
        a = self.D.get('acc') or {}
        return {'alive_max': max(a.get('alive') or [0]), 'alive_end': (a.get('alive') or [0])[-1], 'attacking_max': max(a.get('att') or [0]),
                'attacking_sentinel_s': r(a.get('att_s', 0.0), 1), 'first_attack_s': a.get('first_att'),
                'ahead_attacking_sentinel_s': r(a.get('ahead_s', 0.0), 1), 'ps_pawn_samples': a.get('ps'), 'min_dist_ship2': a.get('min_d2'),
                'safety_cut_s': self.D.get('safety')}

    def tail_series(self, key, secs):
        """the values of series field key in the last secs of the current phase."""
        t0 = self.now - secs
        return [s.get(key) for s in self.R['series'] if s.get('ph') == self.phase and s['t'] >= t0 and s.get(key) is not None]

    def near_frac(self, ref, rng):
        pts = self.snap()
        if not pts:
            return None
        return r(len([p for p in pts if dist(p['loc'], ref) <= rng]) / float(len(pts)), 2)

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
        self.log_tail()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        self.sample()
        el = self.now - self.p_t0
        ph = self.phase
        try:
            getattr(self, 'ph_' + ph, lambda e: None)(el)
        except Exception:  # noqa: BLE001
            self.err('ph_' + ph)
        if el >= self.phases[self.pi][1] or self.D.get('phase_done'):
            self.log_tail(final=False)
            try:
                getattr(self, 'end_' + ph, lambda: None)()
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
        self.line('INFO', 'phase %s (%.0f s)' % (self.phase, self.phases[self.pi][1]))
        try:
            getattr(self, 'start_' + self.phase, lambda: None)()
        except Exception:  # noqa: BLE001
            self.err('start_' + self.phase)

    def find_actors(self):
        try:
            ship_cls = unreal.load_class(None, SHIP_CLS)
            self.pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
            self.char = self.pc.get_controlled_pawn() if self.pc else None
            ss = unreal.GameplayStatics.get_all_actors_of_class(self.w, ship_cls)
            self.ship = ss[0] if ss else None
            sw = self.find_swarm()
            self.R['setup_try'] = {'pc': bool(self.pc), 'char': bool(self.char), 'ship': bool(self.ship), 'swarm': sw}
            if self.pc and self.ship and sw and isinstance(self.char, unreal.Character):
                self.R['setup'].update({'world': self.w.get_path_name(), 'char': self.char.get_name(), 'ship': self.ship.get_name(),
                                        'spawner_pie': self.spawner.get_name(), 'swarm': self.swarm.get_name()})
                self.line('INFO', 'setup %s' % dict((k, self.R['setup'].get(k)) for k in ('world', 'char', 'ship', 'spawner_pie', 'swarm')))
                return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
        return False

    # ================================================================ phases
    # ---- settle: wind off, scheme, the swarm's setup
    def start_settle(self):
        self.wind_off(self.ship)
        self.set_scheme(self.ship, self.cfg['scheme'])
        self.R['setup']['scheme'] = SCHEME_NAMES62.get(self.cfg['scheme'])
        self.bind()
        try:
            t0 = self.turrets(self.ship)
            if t0:
                self.pivot_h = float(gp(t0[0], 'PivotHeight', 'pivot_height', default=150.0) or 150.0)
        except Exception:  # noqa: BLE001
            self.err('pivot')
        rules = {}
        try:
            gm = unreal.GameplayStatics.get_game_mode(self.w)
            ru = gp(gm, 'SentinelSwarmRules', 'sentinel_swarm_rules')
            rules['game_mode'] = gm.get_class().get_name() if gm else None
            rules['asset'] = ru.get_path_name() if ru else None
            if ru:
                for n in ('max_attackers_per_player', 'max_target_distance', 'retarget_interval', 'sentinel_attack_effect', 'max_alive_sentinels'):
                    v = gp(ru, n)
                    rules[n] = v.get_name() if hasattr(v, 'get_name') else (r(v) if isinstance(v, float) else v)
        except Exception:  # noqa: BLE001
            self.err('rules')
        self.R['setup']['rules'] = rules
        self.line('INFO', 'swarm rules %s; trait %s; pivot height %s; mounts %s' % (rules, self.params, self.pivot_h, self.mounts))

    def end_settle(self):
        ok = valid(self.spawner) and self.swarm is not None and self.R['setup'].get('delegates_bound', 0) == 2
        rules = self.R['setup'].get('rules') or {}
        self.check('setup_swarm', 'PASS' if ok and rules.get('asset') else ('WARN' if ok else 'FAIL'),
                   'PIE spawner %s, swarm subsystem %s, OnSentinelKilled / Damaged bound %s, GameMode %s rules %s (no rules: the class '
                   'defaults: attack effect UMechSentinelAttackEffect)' % (
                       self.spawner.get_name() if valid(self.spawner) else None, self.swarm.get_name() if self.swarm else None,
                       self.R['setup'].get('delegates_bound'), rules.get('game_mode'), rules.get('asset')), rules)

    # ---- ship 2: the undriven, unmanned ship near the swarm (c1)
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
            self.teleport(self.ship2, P2, 0.0)

    def end_spawn2(self):
        self.check('setup_ship2', 'PASS' if valid(self.ship2) else 'FAIL', 'ship 2 spawned and parked at %s: %s' % (
            P2, self.ship2.get_name() if valid(self.ship2) else None))

    # ---- board
    def start_board(self):
        self.cmd('Aura.Airship.Board 0')

    def end_board(self):
        ok = same(self.pawn(), self.ship) and same(self.ship.get_pilot(), self.char)
        self.check('setup_board', 'PASS' if ok else 'FAIL', 'player 0 at the helm of ship 1: %s' % ok)

    # ---- (a) + (c1): ship 1 driven, hovering at P1; ship 2 parked 50 m to starboard
    def start_s_pilot(self):
        if not same(self.pawn(), self.ship):
            self.cmd('Aura.Airship.Board 0')
        self.teleport(self.ship, P1, 0.0)
        if valid(self.ship2):
            self.teleport(self.ship2, P2, 0.0)

    def ph_s_pilot(self, el):
        if el >= 0.4 and 'base' not in self.D:
            self.D['base'] = {'s1': self.ship_hp(self.ship), 's2': self.ship_hp(self.ship2), 'pilot': self.health(self.char),
                              't': self.thp(self.ship), 'pilot_tele': self.tele(self.ship).get('PilotHealth')}
            self.D['healed'] = 0.0
        if el >= 0.5 and 'wave' not in self.D:
            self.D['wave'] = self.start_wave(SP_A, 1)
        if el >= 15.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('a_swarm_t15', 'side', self.ship)
        if el >= 22.0 and 'cap2' not in self.D:
            self.D['cap2'] = True
            self.capture('a_swarm_t22', 'player')

    def end_s_pilot(self):
        b = self.D.get('base') or {}
        e = {'s1': self.ship_hp(self.ship), 's2': self.ship_hp(self.ship2), 'pilot': self.health(self.char), 't': self.thp(self.ship)}
        acc = self.acc_summary()
        q1 = self.target_point(self.ship)
        frac = self.near_frac(q1, self.exit_range())
        psn = acc.get('ps_pawn_samples') or {}
        ps_ship = psn.get(self.ship.get_name(), 0)
        ps_all = sum(psn.values())
        d_end = self.tail_series('d1', 5.0)
        ok1 = ps_all and ps_ship == ps_all and acc['attacking_max'] >= 1 and frac is not None and frac >= 0.6
        self.check('SW.a1_target_driven_ship', 'PASS' if ok1 else ('WARN' if self.D.get('safety') else 'FAIL'),
                   'ship 1 driven at P1, wave 1 (%d) from 55 m to port: PlayerState pawn = ship 1 in %d of %d samples (want all: the pilot is '
                   'no target of its own), first attack at %s s, attacking at most %d, %s of the alive sentinels within the exit range '
                   '(%.0f cm) of ship 1\'s target point at the end (want >= 0.6), median distance last 5 s %s cm (orbit radius %.0f +- 25 %%)%s'
                   % (self.cfg['count'], ps_ship, ps_all, acc['first_attack_s'], acc['attacking_max'], frac, self.exit_range(),
                      r(median(d_end), 0) if d_end else None, self.params['orbit_radius'],
                      '; SAFETY CUT at %s s (no swarm left at the end)' % self.D['safety'] if self.D.get('safety') else ''), acc)
        loss = (b['s1'] - e['s1']) if b.get('s1') is not None and e['s1'] is not None else None
        tl, td = self.tagged('s_pilot', self.ship.get_name())
        other = r(loss - td, 2) if loss is not None else None
        self.check('T3.5_swarm_hull', 'PASS' if loss and loss > 0.0 else 'FAIL',
                   'real swarm on the driven ship for 30 s (no TestBullet): ship 1 %s -> %s (loss %s); tagged path naming the ship (log) '
                   '%d hits / %s damage; the rest %s came through the Pawn sweep (PA boxes of the driven, player-controlled ship); '
                   '%s attacking sentinel-seconds (~%s bullets at AttackSpeed %s)' % (
                       b.get('s1'), e['s1'], r(loss, 2) if loss is not None else None, tl, td, other, acc['attacking_sentinel_s'],
                       r(acc['attacking_sentinel_s'] * self.params.get('attack_speed', 0.6), 0), self.params.get('attack_speed')),
                   {'tagged_by_target': self.log_counts.get('s_pilot'), 'turrets': [b.get('t'), e['t']]})
        healed = self.D.get('healed', 0.0)
        pl = (b['pilot'] - e['pilot'] + healed) if b.get('pilot') is not None and e['pilot'] is not None else None
        want = loss * self.share if loss is not None else None
        ok3 = loss and pl is not None and abs(pl - want) <= 0.5 + 0.03 * want and not self.D.get('safety')
        self.check('SW.a2_pilot_crew_share', 'PASS' if ok3 else ('WARN' if self.D.get('safety') else 'FAIL'),
                   'pilot %s -> %s (+ %s topped up inside the phase: loss %s) for a ship loss of %s: want %s x %s = %s (+-0.5 + 3 %%); '
                   'the pilot is not player controlled while he drives, so no bullet is his own%s' % (
                       b.get('pilot'), e['pilot'], healed, r(pl, 2) if pl is not None else None, r(loss, 2) if loss is not None else None,
                       self.share, r(loss, 2) if loss is not None else None, r(want, 2) if want is not None else None,
                       '; SAFETY CUT at %s s' % self.D['safety'] if self.D.get('safety') else ''), {'topups': self.D.get('topups')})
        t0, t1 = b.get('t') or [None, None], e['t']
        self.D['a_end'] = e
        tloss = [r(t0[i] - t1[i], 2) if t0[i] is not None and t1[i] is not None else None for i in (0, 1)]
        tsum = sum(x for x in tloss if x)
        bullets = acc['attacking_sentinel_s'] * self.params.get('attack_speed', 0.6)
        if not self.aim_chance:
            st3 = 'INFO'                             # no aim redirect in this build (or off): nothing can reach a turret
        else:
            st3 = 'PASS' if tsum > 0.0 else ('WARN' if bullets * self.aim_chance < 5.0 or self.D.get('safety') else 'FAIL')
        self.check('SW.a3_turrets_plain_hover', st3, 'turret losses in the plain hover %s (tagged lines on turrets %s) of ~%s bullets; the '
                   'swarm orbits the ship\'s root at ~%s cm and the turrets sit %s cm forward of it, so only bullets aimed at a turret '
                   '(Settings.SwarmTurretAimChance %s: want > 0 when that is on) reach one; ship loss %s in the same time' % (
                       tloss, dict((k, v) for k, v in (self.log_counts.get('s_pilot') or {}).items() if 'Turret' in k), r(bullets, 0),
                       self.params['orbit_radius'], self.mounts[0]['loc'][0], self.aim_chance, r(loss, 2) if loss is not None else None))
        if valid(self.ship2):
            s2l = (b['s2'] - e['s2']) if b.get('s2') is not None and e['s2'] is not None else None
            n2, d2 = self.tagged('s_pilot', self.ship2.get_name())
            md = acc.get('min_dist_ship2')
            near = md is not None and md <= 10000.0
            if s2l is not None and abs(s2l) < 0.01:
                st = 'PASS' if near else 'WARN'
            else:
                st = 'WARN' if (s2l is not None and n2 <= 2 and (md is None or md > self.exit_range())) else 'FAIL'
            self.check('SW.c1_undriven_ship_near', st, 'ship 2 (undriven, unmanned) parked 50 m from the driven ship 1 for 30 s: %s -> %s '
                       '(want unchanged: not a target); nearest sentinel to ship 2\'s root %s cm (want <= 100 m to count as near); tagged '
                       'hits on it %d (a stray bullet may hit an undriven ship, D3: WARN when <= 2 and no sentinel came within the exit range)'
                       % (b.get('s2'), e['s2'], md, n2))

    # ---- (b): the player leaves the helm and mans a station on ship 1 (now undriven)
    def start_s_gunner(self):
        self.heal_if_low()
        if dist(v3(self.ship.get_actor_location()), P1) > 3000.0 and same(self.pawn(), self.ship):
            self.teleport(self.ship, P1, 0.0)

    def ph_s_gunner(self, el):
        st = self.cfg['station']
        if el >= 0.4 and 'exit' not in self.D:
            self.D['exit'] = True
            if same(self.pawn(), self.ship):
                self.cmd('Aura.Airship.Exit 0')
        if el >= 1.0 and 'mount' not in self.D:
            self.D['mount'] = True
            self.cmd('Aura.Airship.Mount 0 %d' % st)
        if el >= 1.2 and 'wave' not in self.D:
            self.D['wave'] = len(self.snap())
            if self.D['wave'] < 2:
                self.start_wave(SP_A, 1)
        if el >= 2.5 and 'base' not in self.D:
            g = self.gunner(self.ship, st)
            self.D['base'] = {'s1': self.ship_hp(self.ship), 't': self.thp(self.ship), 'g': self.health(self.char),
                              'gunner_ok': same(g, self.char), 'att': self.char.get_attach_parent_actor().get_name() if valid(self.char) and self.char.get_attach_parent_actor() else None,
                              'driven': self.ship.get_pilot() is not None, 'mode': self.tele(self.ship).get('UnpilotedMode')}
            self.D['tagged0'] = dict((k, list(v)) for k, v in (self.log_counts.get('s_gunner') or {}).items())
            self.D['healed'] = 0.0
            self.line('INFO', 'gunner baseline %s' % self.D['base'])
        if el >= 14.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('b_gunner_t14', 'gunner', self.ship)
        if el >= 24.3 and 'dm' not in self.D:
            self.D['dm'] = True
            self.D['end'] = {'s1': self.ship_hp(self.ship), 't': self.thp(self.ship), 'g': self.health(self.char),
                             'healed': self.D.get('healed', 0.0)}
            self.cmd('Aura.Airship.Dismount 0')

    def end_s_gunner(self):
        b, e = self.D.get('base') or {}, self.D.get('end') or {'s1': self.ship_hp(self.ship), 't': self.thp(self.ship), 'g': self.health(self.char)}
        acc = self.acc_summary()
        psn = acc.get('ps_pawn_samples') or {}
        cn = self.char.get_name() if valid(self.char) else None
        # samples after the mount (the first 2.5 s include the exit and the on-foot moment)
        ps_char = len([s for s in self.R['series'] if s.get('ph') == 's_gunner' and s['t'] >= self.p_t0 + 2.5 and s.get('ps') == cn])
        ps_all = len([s for s in self.R['series'] if s.get('ph') == 's_gunner' and s['t'] >= self.p_t0 + 2.5])
        dc, d1 = self.tail_series('dc', 8.0), self.tail_series('d1', 8.0)
        frac = self.near_frac(self.target_point(self.char), self.exit_range()) if valid(self.char) else None
        ok1 = b.get('gunner_ok') and not b.get('driven') and ps_all and ps_char == ps_all and dc and d1 and median(dc) < median(d1) and frac is not None and frac >= 0.6
        self.check('SW.b1_target_gunner', 'PASS' if ok1 else ('WARN' if self.D.get('safety') and b.get('gunner_ok') else 'FAIL'),
                   'Exit + Mount 0 %d on ship 1 (gunner %s, attached to %s, ship driven %s, unpiloted mode %s): PlayerState pawn = the '
                   'character in %d of %d samples after the mount (want all: the gunner is a character with a PlayerState; the undriven '
                   'ship is no target), median distance of the swarm to the gunner\'s target point %s cm vs to ship 1\'s %s cm over the '
                   'last 8 s (want gunner < ship: the swarm re-centred), %s within the exit range of the gunner (want >= 0.6)%s' % (
                       self.cfg['station'], b.get('gunner_ok'), b.get('att'), b.get('driven'), b.get('mode'), ps_char, ps_all,
                       r(median(dc), 0) if dc else None, r(median(d1), 0) if d1 else None, frac,
                       '; SAFETY CUT at %s s (no swarm left at the end)' % self.D['safety'] if self.D.get('safety') else ''), acc)
        sl = (b['s1'] - e['s1']) if b.get('s1') is not None and e.get('s1') is not None else None
        healed = e.get('healed', self.D.get('healed', 0.0))
        gl = (b['g'] - e['g'] + healed) if b.get('g') is not None and e.get('g') is not None else None
        t0, t1 = b.get('t') or [None, None], e.get('t') or [None, None]
        tl = [r(t0[i] - t1[i], 2) if t0[i] is not None and t1[i] is not None else None for i in (0, 1)]
        share = r(sl * self.share, 2) if sl is not None else None
        direct = r(gl - sl * self.share, 2) if gl is not None and sl is not None else None
        tg = {}
        for k, v in (self.log_counts.get('s_gunner') or {}).items():
            v0 = (self.D.get('tagged0') or {}).get(k, [0, 0.0])
            tg[k] = [v[0] - v0[0], r(v[1] - v0[1], 2)]
        total = sum(x for x in [sl, gl] + tl if x)
        ok2 = total > 0.0 and direct is not None and direct >= -0.5 - 0.03 * (share or 0.0) and not self.D.get('safety')
        self.check('SW.b2_gunner_damage', 'PASS' if ok2 else ('WARN' if self.D.get('safety') else 'FAIL'),
                   'over ~22 s at the gun: ship 1 loss %s (undriven: only the tagged path, a PA box met before the gunner or the '
                   'HitBox), turret losses %s, gunner loss %s = crew share %s (%s x ship loss) + direct %s (~%s hits of %s); '
                   'tagged-path hits by target %s (want some damage, and the gunner at least his share); %s topped up inside the '
                   'phase (%d times, counted in his loss)%s' % (
                       r(sl, 2) if sl is not None else None, tl, r(gl, 2) if gl is not None else None, share, self.share, direct,
                       r(direct / max(0.01, self.params.get('attack_damage', 3.0)), 1) if direct is not None else None, self.params.get('attack_damage'),
                       tg, healed, len(self.D.get('topups') or []),
                       '; SAFETY CUT at %s s' % self.D['safety'] if self.D.get('safety') else ''), {'tagged': tg, 'topups': self.D.get('topups')})
        ti = self.cfg['station'] - 4 if self.cfg['station'] >= 4 else None
        if ti is not None:
            tn = (self.turret(self.ship, ti).get_name() if self.turret(self.ship, ti) else None)
            v = tl[ti]
            self.check('SW.b3_turret_hits_real', 'PASS' if v and v > 0.0 else 'WARN',
                       'turret %d (the gunner\'s, %s): loss %s from real sentinel bullets aimed at its gunner; tagged lines naming it %s '
                       '(a line that met the HitBox first; the hull no longer blocks Visibility, so BulletTargetRedirect only acts on a PA '
                       'box hit right before the HitBox)' % (
                           ti, tn, v, tg.get(tn)))
        self.D['tl_b'] = tl

    # ---- (c2): nobody aboard ship 1 (nor ship 2), the swarm around it, the player far away
    def start_s_empty(self):
        self.heal_if_low()
        if same(self.pawn(), self.ship) or (valid(self.ship) and same(self.ship.get_pilot(), self.char)):
            self.cmd('Aura.Airship.Exit 0')
        elif any(same(self.gunner(self.ship, s), self.char) for s in range(6)):
            self.cmd('Aura.Airship.Dismount 0')

    def ph_s_empty(self, el):
        if 'near0' not in self.D:
            # where the swarm is when the crew has just left: around ship 1 (its root or the gunner's seat 20 m forward)
            pts = self.snap()
            self.D['near0'] = r(len([p for p in pts if dist(p['loc'], self.target_point(self.ship)) <= 4000.0]) / float(len(pts)), 2) if pts else None
        if el >= 0.3 and 'tp' not in self.D:
            self.D['tp'] = self.tp_char(CHAR_FOOT, 0.0)
            if not self.D['tp']:
                self.D.pop('tp')
        if el >= 1.0 and 'wave' not in self.D:
            pts = self.snap()
            near = len([p for p in pts if dist(p['loc'], self.target_point(self.ship)) <= self.exit_range()])
            self.D['wave'] = {'alive': len(pts), 'near_ship1': near}
            if len(pts) < 2:
                self.start_wave((P1[0], P1[1] - 2500.0, P1[2] + 600.0), 1)
                self.D['wave']['spawned'] = True
        if el >= 2.0 and 'base' not in self.D:
            pts = self.snap()
            self.D['base'] = {'s1': self.ship_hp(self.ship), 's2': self.ship_hp(self.ship2), 't': self.thp(self.ship),
                              'd1': r(median(self.stats(pts, self.target_point(self.ship))), 0) if pts else None,
                              'pilot': self.ship.get_pilot() is not None, 'gunners': [s for s in range(6) if self.gunner(self.ship, s) is not None],
                              'char': r(v3(self.char.get_actor_location()), 0) if valid(self.char) else None,
                              'near': self.near_frac(self.target_point(self.ship), self.exit_range())}
            self.line('INFO', 'empty-ship baseline %s' % self.D['base'])
        if el >= 10.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('c_empty_t10', 'side', self.ship)

    def end_s_empty(self):
        b = self.D.get('base') or {}
        pts = self.snap()
        e = {'s1': self.ship_hp(self.ship), 's2': self.ship_hp(self.ship2), 't': self.thp(self.ship),
             'd1': r(median(self.stats(pts, self.target_point(self.ship))), 0) if pts else None,
             'near': self.near_frac(self.target_point(self.ship), self.exit_range())}
        l1 = (b['s1'] - e['s1']) if b.get('s1') is not None and e['s1'] is not None else None
        l2 = (b['s2'] - e['s2']) if b.get('s2') is not None and e['s2'] is not None else None
        t0, t1 = b.get('t') or [None, None], e['t']
        tl = [r(t0[i] - t1[i], 2) if t0[i] is not None and t1[i] is not None else None for i in (0, 1)]
        crewless = not b.get('pilot') and not b.get('gunners')
        unchanged = l1 is not None and abs(l1) < 0.01 and all(x is None or abs(x) < 0.01 for x in tl) and (l2 is None or abs(l2) < 0.01)
        swarm_near = (self.D.get('near0') or 0.0) >= 0.5
        st = ('PASS' if swarm_near else 'WARN') if unchanged and crewless else 'FAIL'
        self.check('SW.c2_empty_ship', st, 'ship 1 left with nobody aboard (pilot %s, gunners %s), the player %s on the start platform: '
                   'over 20 s ship 1 %s -> %s, turrets %s, ship 2 %s -> %s (want all unchanged: an undriven, unmanned ship is not a target); '
                   'the swarm %s within 40 m of ship 1 when the crew left (want >= 0.5: it was there), %s within the exit range at 2 s, %s '
                   'at the end; median distance %s -> %s cm (it went for the player)%s' % (
                       b.get('pilot'), b.get('gunners'), b.get('char'), b.get('s1'), e['s1'], tl, b.get('s2'), e['s2'],
                       self.D.get('near0'), b.get('near'), e['near'], b.get('d1'), e['d1'],
                       '; the swarm was spawned here (s_empty ran without s_gunner): weaker test' if (self.D.get('wave') or {}).get('spawned') else ''),
                   {'wave': self.D.get('wave'), 'acc': self.acc_summary()})

    # ---- (d): the driven ship's turrets against a fresh swarm from ahead; holds for the redirect with real bullets
    def start_s_turret(self):
        self.despawn('s_turret: a fresh wave from ahead')
        if valid(self.ship2):
            self.teleport(self.ship2, PARK2, 0.0)
        self.D['win'] = 'setup'
        self.D['holds'] = []
        self.D['hits_hold'] = 0.0

    def fire_at(self, p):
        self.cmd('Aura.Airship.TurretFire 1 %.0f %.0f %.0f' % tuple(p), quiet=self.local.get('turret_fire_on', False))
        self.local['turret_fire_on'] = True

    def fire_off(self):
        if self.local.get('turret_fire_on'):
            self.cmd('Aura.Airship.TurretFire 0')
            self.local['turret_fire_on'] = False

    def track_fire(self):
        """every 0.1 s: TurretFire at the current target (kept while alive and in an arc), else the nearest in-arc sentinel."""
        if self.now - self.D.get('f_last', -1.0) < 0.099:
            return
        self.D['f_last'] = self.now
        pts = self.snap()
        arc = [p for p in pts if self.in_arc(self.ship, p['loc'], 0) or self.in_arc(self.ship, p['loc'], 1)]
        cur = next((p for p in arc if p['k'] == self.D.get('f_target')), None)
        if cur is None and arc:
            piv = self.world_of(self.ship, [self.mounts[0]['loc'][0], 0.0, self.mounts[0]['loc'][2] + self.pivot_h])
            cur = min(arc, key=lambda p: dist(p['loc'], piv))
            self.D['f_target'] = cur['k']
            self.D.setdefault('f_targets', []).append(cur['k'])
        if cur is None:
            self.fire_off()
            return
        self.fire_at(cur['loc'])
        self.D['f_frames'] = self.D.get('f_frames', 0) + 1

    def hold_step(self, el):
        """keeps one ATTACKING sentinel at hull cfg['hold'] (turret 0's side; mirrored for turret 1) by teleporting the ship
        every frame (yaw 0, velocity 0) to where that puts it next frame (its velocity from the last frame)."""
        H = self.D.get('hold')
        ti = 0 if not self.turret(self.ship, 0) or not call(self.turret(self.ship, 0), 'is_turret_destroyed') else 1
        s = list(self.cfg['hold'])
        if ti == 1:
            s[1] = -s[1]
        if H is not None:
            loc, st = self.sentinel_loc(H['h'])
            if loc is None or st != 'ATTACKING' or self.now - H['t0'] >= self.cfg['hold_s']:
                self.close_hold('done' if loc is not None and st == 'ATTACKING' else 'sentinel %s' % (st or 'gone'))
                H = None
        if self.D['hits_hold'] >= self.cfg['hold_hits'] * self.params.get('attack_damage', 3.0) - 0.01:
            # enough turret hits from the closed holds: no new one (the ship stays where the last hold left it)
            return
        if H is None:
            pts = [p for p in self.snap() if p['st'] == 'ATTACKING']
            if not pts:
                return
            best = min(pts, key=lambda p: dist(self.hull_local(self.ship, p['loc']), s))
            H = {'k': best['k'], 'h': best['h'], 't0': self.now, 'ti': ti, 's': s, 'prev': best['loc'], 'prev_t': self.now,
                 'hp0': self.thp(self.ship)[ti], 'ship0': self.ship_hp(self.ship), 'err': [], 'geom': None, 'n': 0}
            self.D['hold'] = H
            loc = best['loc']
            self.line('INFO', 'hold %d: sentinel %s at hull %s -> %s (turret %d)' % (len(self.D['holds']) + 1, best['k'],
                                                                                   r(self.hull_local(self.ship, loc), 0), r(s, 0), ti))
        else:
            loc, _ = self.sentinel_loc(H['h'])
        H['n'] += 1
        if H['n'] > 2:
            H['err'].append(r(dist(self.hull_local(self.ship, loc), s), 1))
        if H['n'] == 4 and H['geom'] is None:
            q = self.target_point(self.ship)
            tt = self.turret(self.ship, ti)
            hb = tt.get_editor_property('HitBox') if tt else None
            first = self.trace(loc, q, [])
            far = [q[i] + (q[i] - loc[i]) * 0.2 for i in range(3)]
            H['geom'] = {'first': first, 'line_crosses_hitbox': self.comp_hit(hb, loc, far) if hb else None,
                         'hull': r(self.hull_local(self.ship, loc), 1), 'd': r(dist(loc, q), 0)}
            if H.get('cap') is None and len(self.D['holds']) == 0:
                H['cap'] = self.capture('d_hold1', 'hold', self.ship)
        dt = max(1e-3, self.now - H['prev_t'])
        vel = [(loc[i] - H['prev'][i]) / dt for i in range(3)] if self.now > H['prev_t'] else [0.0, 0.0, 0.0]
        H['prev'], H['prev_t'] = loc, self.now
        nxt = [loc[i] + vel[i] / FIXED_FPS62 for i in range(3)]
        self.teleport(self.ship, [nxt[i] - s[i] for i in range(3)], 0.0)

    def close_hold(self, why):
        H = self.D.get('hold')
        if H is None:
            return
        hp1 = self.thp(self.ship)[H['ti']]
        loss = r(H['hp0'] - hp1, 2) if H['hp0'] is not None and hp1 is not None else None
        if loss:
            self.D['hits_hold'] += loss
        rec = {'k': H['k'], 'turret': H['ti'], 'secs': r(self.now - H['t0'], 2), 'why': why, 'turret_loss': loss,
               'ship_loss': r(H['ship0'] - self.ship_hp(self.ship), 2) if H['ship0'] is not None else None,
               'offset_err_cm': {'mean': r(mean(H['err']), 1) if H['err'] else None, 'max': max(H['err']) if H['err'] else None},
               'geom': H['geom']}
        self.D['holds'].append(rec)
        self.R['holds'].append(rec)
        self.line('INFO', 'hold %d closed (%s): %s' % (len(self.D['holds']), why, rec))
        self.D['hold'] = None

    def ph_s_turret(self, el):
        if el >= 0.3 and 'board' not in self.D:
            self.D['board'] = True
            if not same(self.pawn(), self.ship):
                self.cmd('Aura.Airship.Board 0')
        if el >= 0.8 and 'placed' not in self.D:
            self.D['placed'] = True
            self.teleport(self.ship, P1, 0.0)
            self.heal_if_low()
        if el >= 1.2 and 'wave' not in self.D:
            self.D['wave'] = self.start_wave(SP_D, 2)
            self.D['base'] = {'s1': self.ship_hp(self.ship), 'pilot': self.health(self.char), 't': self.thp(self.ship),
                              'shots': self.tshots(self.ship), 'driven': same(self.pawn(), self.ship)}
            self.D['healed'] = 0.0
        win = 'A' if 2.5 <= el < 9.0 else ('H' if 9.0 <= el < 29.0 else ('B' if 29.0 <= el < 44.0 else 'off'))
        if win != self.D.get('win'):
            self.window_edge(self.D.get('win'), win)
            self.D['win'] = win
        if win == 'B' and self.cfg['jump_cm'] > 0.0 and el - self.D.get('jump_el', -99.0) >= self.cfg['jump_s']:
            # the swarm orbits the root behind the turret line: the ship jumps back along -X (yaw 0), so for a moment the
            # sentinels that were ahead of the root are ahead of the turrets, inside their arcs (they then catch up)
            self.D['jump_el'] = el
            p = v3(self.ship.get_actor_location())
            self.teleport(self.ship, [p[0] - self.cfg['jump_cm'], p[1], p[2]], 0.0)
            self.D['jumps'] = self.D.get('jumps', 0) + 1
        if win in ('A', 'B'):
            self.track_fire()
        elif win == 'H':
            self.hold_step(el)
        if el >= 5.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('d_approach_t5', 'bow', self.ship)

    def window_edge(self, old, new):
        """per-window baselines (turrets, ship, kills) and the switches between fire and holds."""
        W = self.D.setdefault('W', {})
        if old in ('A', 'H', 'B'):
            W[old]['t1'] = self.thp(self.ship)
            W[old]['s1'] = self.ship_hp(self.ship)
            W[old]['shots1'] = self.tshots(self.ship)
            W[old]['alive1'] = len(self.snap())
            W[old]['hp1'] = dict((p['k'], p['hp']) for p in self.snap())
        if old in ('A', 'B'):
            self.fire_off()
        if old == 'H' and self.D.get('hold') is not None:
            self.close_hold('window end')
        if new in ('A', 'H', 'B'):
            W[new] = {'t0': self.thp(self.ship), 's0': self.ship_hp(self.ship), 'shots0': self.tshots(self.ship), 'alive0': len(self.snap()),
                      'hp0': dict((p['k'], p['hp']) for p in self.snap()), 'max': dict((p['k'], p['max']) for p in self.snap()),
                      'ahead0': (self.D.get('acc') or {}).get('ahead_s', 0.0), 'el0': r(self.now - self.p_t0, 2)}
        if old in ('A', 'H', 'B'):
            W[old]['ahead_s'] = r((self.D.get('acc') or {}).get('ahead_s', 0.0) - W[old].get('ahead0', 0.0), 1)
        self.line('INFO', 'window %s -> %s' % (old, new))

    def end_s_turret(self):
        if self.D.get('win') in ('A', 'H', 'B'):
            self.window_edge(self.D['win'], 'off')
            self.D['win'] = 'off'
        self.fire_off()
        W = self.D.get('W') or {}
        b = self.D.get('base') or {}

        def tloss(w):
            t0, t1 = (W.get(w) or {}).get('t0') or [None, None], (W.get(w) or {}).get('t1') or [None, None]
            return [r(t0[i] - t1[i], 2) if t0[i] is not None and t1[i] is not None else None for i in (0, 1)]
        shots = dict((w, (W[w].get('shots1') or 0) - (W[w].get('shots0') or 0)) for w in W)
        kills = [k for k in self.R['kills'] if k['ph'] == 's_turret']
        kills_fire = [k for k in kills if k.get('win') in ('A', 'B')]
        dmg = dict((k, v) for k, v in self.R['damage_events'].items() if k.startswith('s_turret|A|') or k.startswith('s_turret|B|'))
        dmg_n = sum(v[0] for v in dmg.values())
        # health drops seen in the snapshots (a second source for T6.7)
        hp_drop = 0.0
        for w in ('A', 'B'):
            ww = W.get(w) or {}
            for k, hp0 in (ww.get('hp0') or {}).items():
                hp1 = (ww.get('hp1') or {}).get(k)
                if hp1 is not None:
                    hp_drop += max(0.0, hp0 - hp1)
                else:
                    hp_drop += max(0.0, hp0)
        sfire = (shots.get('A') or 0) + (shots.get('B') or 0)
        st67 = 'PASS' if dmg_n > 0 or hp_drop > 0.0 else ('FAIL' if sfire > 0 else 'WARN')
        self.check('T6.7_turret_hits_sentinel', st67, 'Aura.Airship.TurretFire at the nearest sentinel in a turret arc (10 Hz) during '
                   '2.5-9 s and 29-44 s: %s turret shots, OnSentinelDamaged %d events %s, health drop in the snapshots %s (want > 0)' % (
                       sfire, dmg_n, dmg, r(hp_drop, 1)), {'targets': self.D.get('f_targets'), 'windows': dict((w, {'el0': W[w].get('el0'), 'alive': [W[w].get('alive0'), W[w].get('alive1')]}) for w in W)})
        self.check('SW.d3_turret_kills', 'PASS' if kills_fire else ('WARN' if (dmg_n or hp_drop) else ('FAIL' if sfire else 'WARN')),
                   'sentinels killed while the turrets fired: %d (%s), %d killed in the whole phase; wave 2 had %d at %s x health; shots '
                   'per window %s; %s jump(s) back of %s cm in the late window' % (
                       len(kills_fire), [(k['t'], k['by']) for k in kills_fire][:8], len(kills), self.cfg['count_d'], self.cfg['d_health'],
                       shots, self.D.get('jumps', 0), self.cfg['jump_cm']), {'kills': kills})
        la, lb = tloss('A'), tloss('B')
        self.check('SW.d1_turret_plain', 'INFO', 'turret losses from real bullets without a hold: approach window %s, late window %s '
                   '(Settings.SwarmTurretAimChance %s); attacking sentinels ahead of the turret line inside the exit range: %s / %s '
                   'sentinel-seconds' % (la, lb, self.aim_chance, (W.get('A') or {}).get('ahead_s'), (W.get('B') or {}).get('ahead_s')))
        holds = self.D.get('holds') or []
        lh = tloss('H')
        hloss = sum(x for x in lh if x)
        geom_ok = [h for h in holds if (h.get('geom') or {}).get('line_crosses_hitbox') and ((h['geom'].get('first') or {}).get('dist') or 0.0) > 5.0
                   and h['secs'] >= 1.8]
        st = 'PASS' if hloss > 0.0 else ('FAIL' if geom_ok else 'WARN')
        self.check('SW.d2_turret_redirect_hold', st, 'holds (%d, %s s in all): one ATTACKING sentinel kept at hull %s, ship driven %s: turret '
                   'losses %s (want > 0: real bullets whose line meets the turret\'s HitBox before anything else that blocks Visibility; '
                   'the hull no longer does); holds with that geometry checked (Python trace: first Visibility hit outside the '
                   'start, the line crosses the HitBox) and >= 1.8 s long: %d%s; tagged lines in the phase %s' % (
                       len(holds), r(sum(h['secs'] for h in holds), 1), r(self.cfg['hold'], 0), b.get('driven'), lh, len(geom_ok),
                       '' if st != 'WARN' else ' (WARN: no hold had the geometry, the harness could not set the line up)',
                       self.log_counts.get('s_turret')), {'holds': holds})
        e = {'s1': self.ship_hp(self.ship), 'pilot': self.health(self.char)}
        loss = (b['s1'] - e['s1']) if b.get('s1') is not None and e['s1'] is not None else None
        healed = self.D.get('healed', 0.0)
        pl = (b['pilot'] - e['pilot'] + healed) if b.get('pilot') is not None and e['pilot'] is not None else None
        want = loss * self.share if loss is not None else None
        ok = loss is not None and pl is not None and abs(pl - want) <= 0.5 + 0.03 * want
        self.check('SW.d4_pilot_crew_share', ('PASS' if ok else 'FAIL') if loss and not self.D.get('safety') else 'INFO',
                   'phase s_turret: ship 1 loss %s, pilot loss %s with %s topped up inside the phase (want %s x = %s)%s' % (
                       r(loss, 2) if loss is not None else None, r(pl, 2) if pl is not None else None, healed, self.share,
                       r(want, 2) if want is not None else None, '; SAFETY CUT at %s s' % self.D['safety'] if self.D.get('safety') else ''),
                   {'topups': self.D.get('topups')})


    # ---- (e) cannonballs against the real swarm (review 2026-11-27, should fix 8). AAirshipCannonball has its own path for
    # sentinels, which have no collision: a sweep of SentinelHitRadius (1 m) along each flight segment (the ball's damage
    # once, the ball flies on) and at the burst a query of SplashRadius (6 m) with the falloff. No earlier run met it with
    # real sentinels. The balls are the ships' own class with the ship as source (AAirshipCannonball::SpawnTestCannonball
    # -> InitCannonball, as a fired one) and the harness aims them: a pilot's broadside cannot be pointed at one orbiting
    # sentinel from Python (the aim is the camera's ray; Point & Fly turns the hull for it).
    #  flight  9-19 s: 3 balls of ship 1 from the muzzle nearest to a sentinel, led by its velocity, the drop compensated
    #  splash 19-31 s: balls of SHIP 2 into ship 1's hull (a ball ignores its own ship) at the point nearest to a sentinel
    #                  1.5-5.6 m off the hull, coming in 2 m above the hull and 3.5 m beside that point, so the path stays
    #                  more than 1 m from the sentinel: what it takes is the burst's splash
    def muzzles_w(self, ship):
        m = ship.get_editor_property('Mesh')
        out = {}
        for c in ('L1', 'L2', 'R1', 'R2'):
            try:
                out[c] = v3(m.get_socket_location('Cannon_%s_Muzzle' % c))
            except Exception:  # noqa: BLE001
                self.err('muzzle_socket')
        return out

    def test_ball(self, loc, vel, source, damage=60.0):
        try:
            cls = unreal.load_class(None, BALL_BP62)
            return unreal.AirshipCannonball.spawn_test_cannonball(self.w, cls, unreal.Vector(*loc), unreal.Vector(*vel), source, float(damage), -1.0)
        except Exception:  # noqa: BLE001
            self.err('test_ball')
            return None

    def hull_closest(self, ship, p):
        """(cm, world point) of the hull collision's point nearest to p, or (None, None)"""
        try:
            res = self.hull(ship).get_closest_point_on_collision(unreal.Vector(*p))
            vals = res if isinstance(res, tuple) else (res,)
            d = next((float(x) for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool)), None)
            q = next((v3(x) for x in vals if isinstance(x, unreal.Vector)), None)
            return d, q
        except Exception:  # noqa: BLE001
            self.err('hull_closest')
            return None, None

    def start_s_cannon(self):
        self.despawn('s_cannon: a fresh wave')
        if valid(self.ship2):
            self.teleport(self.ship2, P2, 0.0)
        self.D.update({'win': 'setup', 'prev': {}, 'vel': {}, 'shots': [], 'dmg': [], 'next': 0.0})

    def ph_s_cannon(self, el):
        D, s = self.D, self.ship
        if el >= 0.3 and 'board' not in D:
            D['board'] = True
            if not same(self.pawn(), s):
                self.cmd('Aura.Airship.Board 0')
        if el >= 0.8 and 'placed' not in D:
            D['placed'] = True
            self.teleport(s, P1, 0.0)
            self.heal_if_low()
        if el >= 1.2 and 'wave' not in D:
            D['wave'] = self.start_wave(SP_A, 1)
            D['base'] = {'s1': self.ship_hp(s), 's2': self.ship_hp(self.ship2)}
        if int(el / 3.0) != D.get('_h'):
            D['_h'] = int(el / 3.0)
            self.heal_if_low(0.6)
        pts = self.snap()
        for p in pts:
            pv = D['prev'].get(p['k'])
            if pv and self.now > pv[0] + 1e-4:
                D['vel'][p['k']] = [(p['loc'][i] - pv[1][i]) / (self.now - pv[0]) for i in range(3)]
            D['prev'][p['k']] = (self.now, p['loc'])
        hp = dict((p['k'], p['hp']) for p in pts)
        for sh in D['shots']:
            if 'hp1' not in sh and el >= sh['el'] + 0.7:
                sh['hp1'] = hp.get(sh['k'])                  # None: gone (killed)
                if sh['win'] == 'splash':
                    sh['ship_hp1'] = self.ship_hp(s)
        win = 'flight' if 9.0 <= el < 19.0 else ('splash' if 19.0 <= el < 32.0 else 'off')
        D['win'] = win
        sl = v3(s.get_actor_location())
        if win == 'flight' and el >= D['next'] and len([x for x in D['shots'] if x['win'] == 'flight']) < 3 and el < 18.0:
            cand = [p for p in pts if p['k'] in D['vel'] and dist(p['loc'], sl) <= 4500.0]
            mz = self.muzzles_w(s)
            if cand and mz:
                D['next'] = el + 1.2
                d, p, name, m = min(((dist(p['loc'], m), p, name, m) for p in cand for name, m in mz.items()), key=lambda x: x[0])
                v = D['vel'][p['k']]
                aim = list(p['loc'])
                for _ in range(3):
                    t = dist(aim, m) / BALL_SPEED62
                    aim = [p['loc'][0] + v[0] * t, p['loc'][1] + v[1] * t, p['loc'][2] + v[2] * t + 0.5 * 980.0 * BALL_GRAVITY62 * t * t]
                dd = dist(aim, m) or 1.0
                self.test_ball(m, [(aim[i] - m[i]) / dd * BALL_SPEED62 for i in range(3)], s)
                D['shots'].append({'win': 'flight', 'el': r(el, 2), 'k': p['k'], 'muzzle': name, 'd_cm': r(d, 0), 'hp0': p['hp'],
                                   'sentinel_cms': r(math.sqrt(sum(x * x for x in v)), 0), 'st': p['st']})
        if win == 'splash' and el >= D['next'] and el < 31.0:
            best = None
            for p in pts:
                d, q = self.hull_closest(s, p['loc'])
                if d is not None and q is not None and 150.0 <= d <= 560.0 and (best is None or d < best[0]):
                    best = (d, q, p)
            D['near_hull'] = D.get('near_hull', 0) + (1 if best else 0)
            if best and valid(self.ship2):
                D['next'] = el + 1.3
                d, q, p = best
                n = [(p['loc'][i] - q[i]) / d for i in range(3)]
                up = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
                t = [n[1] * up[2] - n[2] * up[1], n[2] * up[0] - n[0] * up[2], n[0] * up[1] - n[1] * up[0]]
                tl = math.sqrt(sum(x * x for x in t)) or 1.0
                start = [q[i] + n[i] * 200.0 + t[i] / tl * 350.0 for i in range(3)]
                L = dist(start, q)
                self.test_ball(start, [(q[i] - start[i]) / L * BALL_SPEED62 for i in range(3)], self.ship2)
                D['shots'].append({'win': 'splash', 'el': r(el, 2), 'k': p['k'], 'd_cm': r(d, 0), 'hull_pt': r(self.hull_local(s, q), 0),
                                   'hp0': p['hp'], 'ship_hp0': self.ship_hp(s), 'path_min_cm': r(350.0 * d / L, 0)})

    def end_s_cannon(self):
        D = self.D
        s1, s2 = self.ship.get_name(), self.ship2.get_name() if valid(self.ship2) else None
        ev = D.get('dmg') or []
        fl = [e for e in ev if e[1] == 'flight' and e[4] == s1]
        sp = [e for e in ev if e[1] == 'splash' and e[4] == s2]
        fshots = [x for x in D['shots'] if x['win'] == 'flight']
        sshots = [x for x in D['shots'] if x['win'] == 'splash']
        kills = [k for k in self.R['kills'] if k.get('ph') == 's_cannon']
        full = median([e[3] for e in fl]) if fl else None
        dropped = [x for x in fshots if 'hp1' in x and (x['hp1'] is None or x['hp1'] < x['hp0'] - 1e-3)]
        ok1 = len(fshots) >= 1 and len(fl) >= 1 and len(dropped) >= 1
        self.check('SW.e1_cannonball_flight', 'PASS' if ok1 else 'FAIL', '%d balls of ship 1 (its own class and damage spec, source = the ship) from the '
                   'muzzle nearest to a real sentinel, led by its velocity: %s. OnSentinelDamaged with ship 1 as instigator in that window: %d '
                   'events %s (want >= 1: the flight sweep, 1 m around the ball); shots after which the sentinel aimed at lost health or was gone: '
                   '%d (want >= 1); kills in the phase %s' % (len(fshots), fshots, len(fl), [(e[0], e[2], e[3]) for e in fl], len(dropped),
                                                              [(k['t'], k['k'], k['by'], k.get('win')) for k in kills]),
                   {'shots': fshots, 'events': fl})
        res = []
        for x in sshots:
            es = [e for e in sp if x['el'] <= e[0] <= x['el'] + 0.6]
            for e in es:
                res.append({'shot_el': x['el'], 'sentinel': e[2], 'aimed_at': x['k'], 'd_cm_at_launch': x['d_cm'] if e[2] == x['k'] else None,
                            'damage': e[3], 'of_full': r(e[3] / full, 3) if full else None,
                            'expected_of_full': r(1.0 - 0.7 * min(1.0, x['d_cm'] / 600.0), 3) if e[2] == x['k'] else None})
        burst = [x for x in sshots if x.get('ship_hp0') is not None and x.get('ship_hp1') is not None and x['ship_hp1'] < x['ship_hp0'] - 1e-3]
        part = [q for q in res if q['of_full'] is not None and 0.25 <= q['of_full'] <= 0.98]
        if not sshots:
            st2 = 'WARN'
        else:
            st2 = 'PASS' if (len(sp) >= 1 and len(burst) >= 1 and (len(part) >= 1 or full is None)) else 'FAIL'
        self.check('SW.e2_cannonball_splash', st2, '%d balls of ship 2 into ship 1\'s hull at the point nearest to a sentinel 1.5-5.6 m off it '
                   '(frames with such a sentinel when a shot was due: %s): %s. Ship 1 lost health after %d of them (the ball burst on its hull). '
                   'OnSentinelDamaged with ship 2 as instigator: %d events; per event against the full damage of a flight hit (%s): %s (want '
                   '>= 1 event with a part of the full damage, 0.25-0.98: the falloff 1 -> 0.3 over 6 m; the expected part is for the launch '
                   'distance, the sentinel moves on)' % (len(sshots), D.get('near_hull'), sshots, len(burst), len(sp), full, res),
                   {'shots': sshots, 'events': sp, 'per_event': res})
        self.despawn('s_cannon done')


def write_sw_report(R):
    try:
        L = ['%s  armed %s  reason: %s  game %.1f s  wall %s s' % (R['version'], R['armed_utc'], R.get('reason'), R.get('game_t', 0), R.get('wall_s')),
             'cfg %s' % R.get('cfg'), 'setup %s' % json.dumps(R.get('setup'), default=str)[:4000], '']
        cnt = {}
        for k, c in R['checks'].items():
            cnt[c['status']] = cnt.get(c['status'], 0) + 1
        L.append('checks: %s' % cnt)
        for k, c in R['checks'].items():
            L.append('%-5s %-28s %s' % (c['status'], k, c['summary']))
        L.append('')
        L.append('kills: %s' % [(k['t'], k['ph'], k.get('win'), k['by']) for k in R.get('kills', [])])
        L.append('sentinel damage events (phase|window|instigator: n, damage): %s' % R.get('damage_events'))
        L.append('tagged-path hits per phase and target (log): %s' % R.get('tagged'))
        L.append('holds: %s' % json.dumps(R.get('holds'), default=str)[:3000])
        L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        L.append('hit_info read failures: %s' % R.get('hit_info_err'))
        for k, v in R['errors'].items():
            L.append('--- %s\n%s' % (k, v['last'][-900:]))
        ls = R.get('log_scan') or {}
        L.append('log: %s' % dict((k, v['count']) for k, v in ls.items()))
        L.append('captures: %s' % [s['file'] for s in R.get('shots', [])])
        with open(os.path.join(SWDIR, 'sw_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        pass


_old62 = globals().get('AS62_RUN')
if _old62 is not None and _old62.phase not in ('finished',):
    print('an as_62 run is active (phase %s): stop it first (as_62x_stop.py)' % _old62.phase)
else:
    AS62_RUN = SwarmRun()
    _ok62 = AS62_RUN.arm()
    for _l in AS62_RUN.R['lines']:
        print(_l)
    print('RESULT: %s' % ('ARMED (poll as_62s_status.py; results in Saved/Airship/round2_swarm/)' if _ok62 else 'FAIL: not armed'))
