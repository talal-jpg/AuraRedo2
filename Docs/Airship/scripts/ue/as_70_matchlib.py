# as_70_matchlib.py - shared code of the round 2 PR B harnesses (Docs/Airship/round2/SPEC_B.md sections 3 and 4):
# as_73_verify_b.py, as_74_pie_match.py (standalone), as_75_pie_match_mp.py (listen server, 2 / 3 / 4 players) and
# as_76_regress.py (PR A regression). Not run on its own: each of them execs it into the editor inbox namespace.
# What is here:
#  * as_30's prelude (OUT, v3, r, dist, wrap180, tl_get / tl_set, gp, valid, find_log, FIXED_FPS, SHIP_CLS, BALL_CLS ...)
#  * the PR B class paths, enum name tables and Appendix A's defaults (MB_APPENDIX_A, as_73 compares the CDO with it)
#  * MBRun: the frame-by-frame harness base. Tests are generator methods run one after the other by a Slate post-tick
#    callback (as_59's state machine, written as `yield` steps): `yield` = wait one frame, `yield from self.wait(s)`,
#    `v = yield from self.until(cond, timeout)`. Each test has a game-time budget; a test past it is closed and FAILs.
#  * the match readers: phase / result from AMyGameState's BlueprintPure getters, team ids from AMyPlayerState /
#    AAirshipPawn / UMyTeamLibrary, the lane state from UAirshipLaneComponent::GetLaneState, the lane numbers from the
#    flight telemetry (FAirshipFlightTelemetry lane fields), and everything else from `Aura.Match.Dump <path>` on the
#    server (JSON written by MyMatchConsole.cpp; the keys read are in mb_dump_doc below) and, for a client's own view of
#    the teams, from the lines `Aura.Match.Status` logs on that machine. Team states, rules and lanes have no Python path
#    (Teams is a C array without BlueprintReadOnly, GetTeamState / GetMatchRules return const references).
#  * the log tail: the editor log is read incrementally every frame; LogMatch / LogLane / ... lines are time-stamped
#    with the harness's game time. Match events: the line AMyGameState::MulticastMatchEvent logs on every machine
#    ("LogMatch: event <Name> team <t> value <v> (<role> <world>)"), else the server's own line for that event.
#  * in-memory settings for a run (UMyMatchSettings / UAirshipSettings / UBurrowerSettings class defaults, the CVars
#    Aura.Match.Enable / Aura.Lane.Debug, the fixed frame rate): snapshot at arm, restored at the end, never saved.
import json, math, os, re, time, traceback  # unreal = inbox namespace

MB_PROJECT = os.path.abspath(unreal.Paths.project_dir())
MB_UE = os.path.join(MB_PROJECT, 'Docs/Airship/scripts/ue')
_mb_as30 = os.path.join(MB_UE, 'as_30_pie_smoke.py')
_mb_src = open(_mb_as30).read()
exec(compile(_mb_src[:_mb_src.index('\nclass AsRun')], _mb_as30, 'exec'), globals())   # OUT, v3, r, dist, tl_get ...
MB_SAVED = os.path.abspath(unreal.Paths.project_saved_dir())
MB_MATCH = os.path.join(MB_SAVED, 'Match')
MB_VERSION = 'as_70_matchlib 2026-11-25'

MB_CLS = {
    'gs': '/Script/Aura.MyGameState', 'ps': '/Script/Aura.MyPlayerState', 'gm': '/Script/Aura.MyGameMode',
    'ship': '/Script/Aura.AirshipPawn', 'lane': '/Script/Aura.AirshipLaneComponent', 'turret': '/Script/Aura.AirshipTurret',
    'ball': '/Script/Aura.AirshipCannonball', 'ball_bp': '/Game/Assets/MyShip/Drivable/BP_AirshipCannonball.BP_AirshipCannonball_C',
    'platform': '/Script/Aura.MyHexPlatform', 'spawner': '/Script/Aura.MyHexPathSpawner',
    'waves': '/Script/Aura.MechSentinelWaveSpawner', 'burrower': '/Script/Aura.BurrowerCharacter',
    'bridges': '/Script/Aura.MyHexBridgeSubsystem', 'swarm': '/Script/Aura.MechSentinelSwarmSubsystem',
    'hud': '/Script/Aura.MyMatchHUDWidget', 'settings': '/Script/Aura.MyMatchSettings',
    'airship_settings': '/Script/Aura.AirshipSettings', 'burrower_settings': '/Script/Aura.BurrowerSettings',
    'memory': '/Script/Aura.MyMatchMemorySubsystem', 'teamlib': '/Script/Aura.MyTeamLibrary',
    'projectile_bp': '/Game/Level/Actors/BP_MyProjectile.BP_MyProjectile_C',
    'gun_ge': '/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C',
}
MB_IA = {'IA_LMB': '/Game/Level/PlayerInput/IA_LMB', 'IA_RMB': '/Game/Level/PlayerInput/IA_RMB',
         'IA_Shift': '/Game/Level/PlayerInput/IA_Shift', 'IA_Space': '/Game/Level/PlayerInput/IA_Space',
         'IA_Move': '/Game/Level/PlayerInput/IA_Move'}
for _n in ('IA_AirshipFire', 'IA_AirshipBoard', 'IA_AirshipExit', 'IA_AirshipLook', 'IA_AirshipStrafe', 'IA_AirshipThrottle',
           'IA_AirshipSteer'):
    MB_IA[_n] = '/Game/Assets/MyShip/Drivable/Input/' + _n
# MyMatchTypes.h order (the telemetry carries LaneState / LaneClamp as uint8, the dump as names)
MB_PHASE = ['None', 'WaitingToStart', 'Countdown', 'InProgress', 'Ended', 'Lobby']   # Lobby appended (SPEC_B_LOBBY D1)
MB_TEAMMODE = ['Auto', 'Practice', 'OneVsOne', 'TwoVsTwo']
MB_RESULT = ['None', 'TeamWon', 'Draw', 'PracticeOver']
MB_REASON = ['None', 'Eliminated', 'Forfeit', 'TimeLimit', 'Host']
MB_EVENTS = ['Countdown', 'Started', 'ShipDestroyed', 'ShipRespawned', 'TeamEliminated', 'ForfeitWarning', 'Forfeited',
             'PracticeToVersus', 'Ended', 'ShipUnderAttack', 'ShipReturning', 'TimeWarning',
             'LobbyCancelled', 'LobbyTeamChanged', 'LobbyRulesChanged', 'LobbyReturn']   # lobby events appended (SPEC_B_LOBBY 4.3)
MB_LANE = ['NoLane', 'Cruising', 'Waiting', 'Assist', 'PilotedInLane', 'OutOfLane', 'Parked', 'Returning']
MB_CLAMP = ['None', 'TeamPace', 'PathEnd', 'Blocked', 'NotStarted', 'Ended', 'Bypass', 'Reel']
MB_UNPILOTED = ['None', 'Coast', 'Drift', 'Hold', 'Lane']        # EAirshipUnpilotedMode (AirshipTypes.h)
MB_HULL_HALF_WIDTH = 1130.0       # cm, lanes_map / research_blender (B2.1)
MB_HULL_HALF_LENGTH = 1450.0
# Appendix A (SPEC_B revision 2 + section 7 review fixes): UMyMatchSettings defaults. Struct / array values as Python values.
MB_APPENDIX_A = {
    'MatchMaps': ['StartupMap'], 'MatchStartDelay': 5.0, 'DefaultExpectedPlayers': 2, 'AutoMaxPlayersPerTeam': 0, 'AutoCoopPlayers': 0,
    'bStartAboard': True, 'bRespawnAboard': False, 'bAlternateSides': True, 'bSmallTeamHandicap': True,
    'bTimeLimitCountsHandicap': False, 'bShipHookOutsideMatch': False, 'bSoloPracticeUnlimitedShips': True,
    'ShipRespawnDelay': 10.0, 'ShipSpawnProtection': 15.0, 'ShipSpawnMinEnemyDistance': 25000.0, 'TeamEmptyForfeitSeconds': 30.0,
    'EndScreenSeconds': 20.0, 'bDestroyUntaggedPlacedShipsInVersus': True, 'FallDeathDepth': 8000.0, 'FallDeathMinFallTime': 1.0,
    'bSentinelBulletsHitUndrivenShips': False, 'ShipDamageGunHit': 5.0, 'ShipDamageTurretRound': 4.0,
    'ShipUnderAttackInterval': 5.0, 'MatchNetCullDistance': 60000.0,
    'SwarmPlayerCountBase': 0.6, 'SwarmPlayerCountPerPlayer': 0.4, 'SwarmPlayerCountMax': 2.2,
    'LaneClearance': 2500.0, 'LaneHeight': 200.0, 'LaneSampleStep': 500.0, 'LaneSmoothHalfWindow': 2500.0, 'LaneBackReach': 6000.0,
    'LaneEndMargin': 5000.0, 'LaneSpawnU': 0.0, 'MaxYawForEnvelope': 80.0, 'FallbackLaneHalfWidth': 10000.0,
    'FallbackLaneLength': 150000.0, 'LaneSpeed': 600.0, 'LaneCatchUpSpeed': 2800.0, 'LanePaceGain': 0.3, 'LanePaceOffset': 1500.0,
    'LaneMaxLead': 4000.0, 'LaneAccel': 250.0, 'LaneMaxTargetLead': 1500.0, 'LaneJoinStep': 1000.0, 'LaneKp': 0.4, 'LaneKd': 0.8,
    'LaneAccelMax': 600.0, 'LaneClimbRate': 200.0, 'LaneZoneEnterLateral': 2000.0, 'LaneZoneEnterVertical': 1500.0,
    'LaneZoneExitLateral': 4000.0, 'LaneZoneExitVertical': 2500.0, 'LaneParkSpeed': 800.0, 'LaneParkSettleTime': 0.5,
    'LaneAssistDelay': 1.0, 'LaneAssistMaxSpeed': 1500.0, 'LaneLookAheadMin': 1500.0, 'LaneLookAheadTime': 3.0,
    'LaneSweepInterval': 0.25, 'LaneBlockedClearChecks': 3, 'LaneOutDriftMaxDistance': 30000.0, 'LaneBlockedTimeout': 5.0,
    'LaneBypassOffset': 3500.0, 'bShipRecall': True, 'ShipRecallDelay': 20.0, 'ShipRecallSpeed': 2500.0,
    'ShipRecallCrossHeight': 8000.0, 'ShipRecallClimbRate': 600.0, 'ShipRecallMaxTime': 60.0, 'ShipRecallMaxDistance': 100000.0, 'ShipRecallBlockedTime': 10.0,
    'LaneHintInterval': 0.25,
}
MB_APPENDIX_A_RULES = {'TeamMode': 'Auto', 'ShipLives': 3, 'SwarmDifficulty': 1, 'TimeLimitMinutes': 15, 'bFriendlyFire': False,
                       'bGrappleShips': True, 'bLaneAssist': True}
MB_APPENDIX_A_FIXED = {'TeamLaneSide': [1, -1], 'TeamColors': [(0.25, 0.66, 0.96), (0.96, 0.54, 0.25)], 'TeamNames': ['BLUE', 'ORANGE']}
# B5.4 table: Count, Health, Armor, Damage, AttackSpeed, MoveSpeed, SelfBuffChance, MaxAlive, MaxAttackersPerPlayer,
# BurrowerSpawnIntervalScale, BurrowerMaxAlivePerPlayer, BurrowerLevel
MB_PRESET_KEYS = ['Count', 'Health', 'Armor', 'Damage', 'AttackSpeed', 'MoveSpeed', 'SelfBuffChance', 'MaxAlive',
                  'MaxAttackersPerPlayer', 'BurrowerSpawnIntervalScale', 'BurrowerMaxAlivePerPlayer', 'BurrowerLevel']
MB_PRESETS = [('Easy', [0.6, 0.7, 0.75, 0.6, 0.85, 0.9, 0.5, 0.6, 6, 1.5, 0, 1]),
              ('Normal', [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0, 1.0, 0, 1]),
              ('Hard', [1.3, 1.3, 1.15, 1.3, 1.1, 1.05, 1.25, 1.2, 12, 0.8, 0, 2]),
              ('Very Hard', [1.6, 1.6, 1.3, 1.6, 1.2, 1.1, 1.5, 1.4, 14, 0.65, 2, 3]),
              ('Nightmare', [2.0, 2.0, 1.5, 2.0, 1.3, 1.15, 2.0, 1.6, 16, 0.5, 2, 4])]
# Every scalar UMyMatchSettings value a run may change (snapshot at arm, written back at the end)
MB_SETTING_NAMES = ['MatchMaps', 'DefaultRules'] + [k for k in MB_APPENDIX_A if k != 'MatchMaps']
MB_EVENT_RE = re.compile(r'LogMatch:.*?\bevent (?:EMyMatchEvent::)?(\w+) team (\d+) value (-?\d+)(?:\s*\((\w+)\s*([^)]*)\))?')
# the server's own log line next to each MulticastMatchEvent (MyGameMode.cpp, AirshipLaneComponent.cpp): the fallback
MB_EVENT_FALLBACK = {'ShipDestroyed': ('Team ships:', ' destroyed, '), 'ShipReturning': ('LogLane', 'recall to its lane'),
                     'TimeWarning': ('LogMatch: Match: ', ' s left'), 'ForfeitWarning': ('LogMatch: Match: ', 'has no players'),
                     'Ended': ('LogMatch: Match: ', 'phase Ended'), 'Countdown': ('LogMatch: Match: ', 'phase Countdown'),
                     'Started': ('LogMatch: Match: ', 'phase InProgress'), 'ShipUnderAttack': ('Team ships:', 'under attack'),
                     'PracticeToVersus': ('LogMatch: Match: ', 'practice -> versus')}
MB_TEAM_NAMES = ['BLUE', 'ORANGE']
MB_STATUS_TEAM_RE = re.compile(r'LogMatch:\s+(BLUE|ORANGE): (active|inactive), (\d+) player\(s\), lives (-?\d+) \(\+(-?\d+) bonus\), '
                               r'lost (-?\d+), side (-?\d+), hull (\d+) %, ship (\S+)(?: \((\w+)\))?(.*)$')
MB_LOG_KEEP = ('LogMatch', 'LogLane', 'LogAirship', 'LogGrapple', 'LogBurrower', 'LogMechSentinel', 'LogBeam', 'LogNet:',
               'PreLogin', 'That match is full', 'Error:', 'Ensure condition failed', 'Accessed None', 'Command not recognized',
               'Repeating last play command', '*** Client: Error for', '*** Server: Error for')

mb_dump_doc = '''Aura.Match.Dump [path] (server; MyMatchConsole.cpp BuildDump) keys the PR B harnesses read: map, server_time,
match_on, phase (WaitingToStart / Countdown / InProgress / Ended / None), phase_end_in_s, time_left_s, expected_players,
round, versus, result, end_reason, winning_team, lead_spline_distance, rules{teams, ship_lives, swarm, time_limit_min,
friendly_fire, grapple_ships, lane_assist}, has_lanes, lane_start_u_m, path_end_u_m, cruise_end_u_m,
teams[{team, name, active, players, lives_left, bonus_lives, ships_lost, lane_side, ship_health_pct, ship,
ship_respawn_in_s, empty_for_s, eliminated, front_u_m}], ships[{name, team, alive, location, velocity, yaw, protected,
protection_left_s, piloted, pilot, speed_ms, health, max_health, u_m, lane_state, lane_side, lane_u_m,
lane_lateral_error_m, lane_vertical_error_m, lane_target_u_m, lane_target_speed_ms, lane_clamp, lane_bypass_m,
recall_in_s, lane_update_ms (M6.2: not written yet, asked for)}], players[{name, team, pawn_class, ship_borne,
platform_spline_distance, health, location, u_m, lateral_from_path_m, dead}] (GameState PlayerArray order = join order).
A client's view of the teams comes from Aura.Match.Status on that machine (mb_status_teams).'''


def mb_nz(x, names=None):
    """canonical lower-case name of an enum value (unreal enum, 'EMyLaneState::Cruising', 'IN_PROGRESS', 3 with names)"""
    if x is None:
        return None
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, (int, float)) and names is not None:
        i = int(x)
        return mb_nz(names[i]) if 0 <= i < len(names) else str(i)
    n = getattr(x, 'name', None)
    s = n if isinstance(n, str) else str(x)
    s = s.split('::')[-1].split('.')[-1].strip('<> ')
    if names is not None:
        try:
            return mb_nz(names[int(float(s))])
        except (ValueError, IndexError):
            pass
    return re.sub('[^a-z0-9]', '', s.lower())


def mb_parse_export(txt):
    """'(A=1.0,B=(0.1,0.2),C=True)' -> dict; nested parentheses become lists (as_59's parse_export)."""
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
            return v.strip('"')
    out = {}
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            out[k.strip()] = conv(v)
    return out


def mb_get(d, *path, **kw):
    """d[k1][k2]... with None (or kw default) for anything missing"""
    for k in path:
        try:
            d = d[k]
        except Exception:  # noqa: BLE001
            return kw.get('default')
        if d is None:
            return kw.get('default')
    return d


def mb_mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def mb_median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def mb_same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def mb_name(a):
    try:
        return a.get_name() if a is not None else None
    except Exception:  # noqa: BLE001
        return None


def mb_pid(ps):
    """APlayerState::GetPlayerId (a BlueprintGetter), else its PlayerId property"""
    try:
        return int(ps.get_player_id())
    except Exception:  # noqa: BLE001
        return int(ps.get_editor_property('player_id'))


def mb_cls(key):
    return unreal.load_class(None, MB_CLS[key])


def mb_cdo(key):
    return unreal.get_default_object(mb_cls(key))


def mb_isa(obj, key):
    """obj's class is MB_CLS[key] or a child of it (isinstance needs the Python wrapper type, which a BP class lacks)"""
    try:
        return obj is not None and bool(unreal.MathLibrary.class_is_child_of(obj.get_class(), mb_cls(key)))
    except Exception:  # noqa: BLE001
        return False


def mb_objects(key, world=None):
    """every live object of a native PR B class (ObjectIterator takes the Python wrapper type), optionally of one world"""
    t = getattr(unreal, MB_CLS[key].split('.')[-1], None)
    if t is None:
        return []
    out = []
    for o in unreal.ObjectIterator(t):
        try:
            if world is None or mb_same(o.get_world(), world):
                out.append(o)
        except Exception:  # noqa: BLE001
            continue
    return out


def mb_cvar_int(name, default=None):
    try:
        return int(unreal.SystemLibrary.get_console_variable_int_value(name))
    except Exception:  # noqa: BLE001
        return default


def mb_editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def mb_editor_cmd(c):
    unreal.SystemLibrary.execute_console_command(mb_editor_world(), c)


def mb_value_text(v):
    """a setting value for the restore file and the report"""
    try:
        if hasattr(v, 'export_text'):
            return v.export_text()
    except Exception:  # noqa: BLE001
        pass
    try:
        return [mb_value_text(x) for x in v] if isinstance(v, (list, tuple)) or type(v).__name__ == 'Array' else str(v)
    except Exception:  # noqa: BLE001
        return str(v)


def mb_set_struct(st, name, field, value):
    """st.<name>.<field> = value for a struct property of a class default (DefaultRules.SwarmDifficulty ...)"""
    s = st.get_editor_property(name)
    s.set_editor_property(field, value)
    st.set_editor_property(name, s, unreal.PropertyAccessChangeNotifyMode.NEVER)


def mb_team_mode(name):
    return getattr(unreal.MyTeamMode, {'auto': 'AUTO', 'practice': 'PRACTICE', 'onevsone': 'ONE_VS_ONE',
                                       'twovstwo': 'TWO_VS_TWO'}[mb_nz(name)])


# --------------------------------------------------------------------------------------------------------------- run
class MBRun(object):
    """Base of the PR B PIE harnesses. Subclasses set TAG (file prefix), OUTDIR, VERSION and implement build_tests() ->
    [(test name, game-second budget, generator method)], find_actors() and refind() (map reloads)."""
    TAG = 'mb'
    VERSION = MB_VERSION
    OUTDIR = MB_MATCH
    TEMP = 'TEMP_MB_'

    def __init__(self):
        self.R = {'version': self.VERSION, 'lib': MB_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'checks': {}, 'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'xgrabs': [], 'done': False,
                  'setup': {}, 'cfg': {}, 'tests': [], 'match_events': [], 'dumps': {}}
        self.orig = {}
        self.cfg = {}
        self.handle = None
        self.phase = 'arming'
        self.tests = []
        self.ti = -1
        self.gen = None
        self.test = None
        self.t_test0 = 0.0
        self.step = ''
        self.now = 0.0
        self.t_base = 0.0
        self.t_world0 = None
        self.wall0 = time.time()
        self.end_wall = 0.0
        self.last_sample = -1.0
        self.last_status = 0.0
        self.frames = 0
        self.D = {}
        self.w = None
        self.worlds = []
        self.user_play = False
        self.log_file = find_log()
        self.log_pos = os.path.getsize(self.log_file) if self.log_file else 0
        self.log_off = self.log_pos
        self.log_part = ''
        self.logl = []
        self.mevents = []
        self.subs = {}
        self.acts = {}
        self.cap = {}
        self.cap_dead = {}
        self.ncap = 0
        self.max_caps = 30
        self.dump_cache = {}
        self.dump_fail = 0
        self.frame = None          # lane frame: O (x, y, z), yaw, H (path half width, cm)
        self.cmds_run = []
        self.seen_ships = set()
        self.attrs = {}
        for n in ('Health', 'MaxHealth'):
            a = unreal.GameplayAttribute()
            a.import_text('(AttributeName="%s",Attribute=/Script/Aura.MyAttributeSet:%s,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")' % (n, n))
            self.attrs[n] = a

    # ------------------------------------------------------------------------------------------------- output
    def path(self, name):
        return os.path.join(self.OUTDIR, '%s_%s' % (self.TAG, name))

    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.test or self.phase, msg)
        self.R['lines'].append(s)
        try:
            with open(self.path('log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def check(self, key, status, msg, data=None):
        """status PASS / FAIL / WARN / INFO / SKIP; key = the spec test id plus a short name (T2.1_pace)"""
        self.R['checks'][key] = {'status': status, 'summary': msg, 'data': data, 't': r(self.now), 'test': self.test}
        self.line(status, '%s: %s' % (key, msg))

    def ok(self, cond):
        return 'PASS' if cond else 'FAIL'

    def event(self, name, **kw):
        kw.update({'event': name, 't': r(self.now), 'test': self.test})
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
        left = sum(b for _, b, _ in self.tests[self.ti + 1:]) if self.tests and self.ti >= 0 else None
        return '%s phase %s test %s (%d/%d) step "%s" game_t %.1f wall %.0f s frames %d checks %s, at most %s game s left, done %s, reason %s' % (
            self.TAG, self.phase, self.test, self.ti + 1, len(self.tests), self.step[:80], self.now, time.time() - self.wall0, self.frames,
            c, None if left is None else int(left), self.R['done'], self.R.get('reason'))

    def write(self, force=False):
        if time.time() - self.last_status >= 2.0 or force:
            self.last_status = time.time()
            try:
                with open(self.path('status.txt'), 'w') as f:
                    f.write(self.status_text() + '\n')
            except Exception:  # noqa: BLE001
                pass
        if not force:
            return
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        self.R['match_events'] = self.mevents[-400:]
        try:
            with open(self.path('result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
        except Exception:  # noqa: BLE001
            pass

    def report(self):
        R = self.R
        try:
            L = ['%s  armed %s  reason: %s  game %.1f s  wall %s s' % (R['version'], R['armed_utc'], R.get('reason'), R.get('game_t') or 0,
                                                                     R.get('wall_s')),
                 'cfg %s' % json.dumps(R.get('cfg'), default=str), 'setup %s' % json.dumps(R.get('setup'), default=str), '']
            cnt = {}
            for c in R['checks'].values():
                cnt[c['status']] = cnt.get(c['status'], 0) + 1
            L.append('checks: %s' % cnt)
            for k, c in sorted(R['checks'].items(), key=lambda kv: (kv[1]['t'] if isinstance(kv[1]['t'], (int, float)) else 0)):
                L.append('%-5s %-36s %s' % (c['status'], k, c['summary']))
            L.append('')
            L.append('tests: %s' % R.get('tests'))
            L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
            for k, v in R['errors'].items():
                L.append('--- %s\n%s' % (k, v['last'][-900:]))
            L.append('match events (log): %s' % [(e['t'], e['event'], e['team'], e['value'], e.get('role')) for e in self.mevents[:60]])
            ls = R.get('log_scan') or {}
            L.append('log: %s' % dict((k, v['count']) for k, v in ls.items()))
            for k in ('error', 'ensure', 'accessed_none', 'not_recognized'):
                for s in (ls.get(k) or {}).get('sample', [])[:4]:
                    L.append('    %s: %s' % (k, s[:300]))
            L.append('captures: %s' % [s['file'] for s in R.get('shots', [])])
            L.append('x grabs requested: %s' % R.get('xgrabs'))
            with open(self.path('report.txt'), 'w') as f:
                f.write('\n'.join(L) + '\n')
        except Exception:  # noqa: BLE001
            with open(self.path('report.txt'), 'w') as f:
                f.write('report failed: %s' % traceback.format_exc())

    # ------------------------------------------------------------------------------------------------- settings
    def snapshot_settings(self):
        """class defaults the run may change (Aura.Match.Set / Aura.Airship.Set Settings. write the same objects)"""
        snap = {}
        try:
            st = mb_cdo('settings')
            for n in MB_SETTING_NAMES:
                try:
                    snap[n] = st.get_editor_property(n)
                except Exception:  # noqa: BLE001
                    self.err('snapshot_' + n)
        except Exception:  # noqa: BLE001
            self.err('snapshot_settings')
        self.orig['match_settings'] = snap
        try:
            ast = mb_cdo('airship_settings')
            self.orig['airship_settings'] = dict((n, ast.get_editor_property(n)) for n in (
                'CrewDamageShare', 'DriftSpeed', 'DriftMaxDistance', 'bHoldWhenUnpiloted', 'HoldEngageSpeed', 'bSpawnTurrets'))
        except Exception:  # noqa: BLE001
            self.err('snapshot_airship_settings')
        try:
            bst = mb_cdo('burrower_settings')
            self.orig['burrower'] = dict((n, bst.get_editor_property(n)) for n in ('bEnabled', 'SpawnInterval', 'FirstSpawnDelay'))
            bst.set_editor_property('bEnabled', bool(self.cfg.get('burrower', False)), unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('snapshot_burrower')
        self.orig['cvars'] = dict((n, mb_cvar_int(n)) for n in ('Aura.Match.Enable', 'Aura.Lane.Debug'))
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        self.R['setup']['settings_before'] = dict((k, mb_value_text(v)) for k, v in snap.items())
        try:
            with open(self.path('restore.json'), 'w') as f:
                json.dump(dict((k, dict((n, mb_value_text(x)) for n, x in v.items()) if isinstance(v, dict) else v)
                               for k, v in self.orig.items()), f, indent=1, default=str)
        except Exception:  # noqa: BLE001
            self.err('restore_file')

    def set_setting(self, name, value):
        """a UMyMatchSettings class default for the run (restored at the end); 'DefaultRules.X' sets a rules field"""
        st = mb_cdo('settings')
        if '.' in name:
            a, b = name.split('.', 1)
            mb_set_struct(st, a, b, value)
        else:
            st.set_editor_property(name, value, unreal.PropertyAccessChangeNotifyMode.NEVER)
        self.line('INFO', 'UMyMatchSettings.%s = %s (class default, for the run)' % (name, value))

    def setting(self, name, default=None):
        try:
            st = mb_cdo('settings')
            if '.' in name:
                a, b = name.split('.', 1)
                return st.get_editor_property(a).get_editor_property(b)
            return st.get_editor_property(name)
        except Exception:  # noqa: BLE001
            return default

    def restore_settings(self):
        try:
            st = mb_cdo('settings')
            for n, v in (self.orig.get('match_settings') or {}).items():
                try:
                    st.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
                except Exception:  # noqa: BLE001
                    self.err('restore_' + n)
        except Exception:  # noqa: BLE001
            self.err('restore_match_settings')
        for key, cls in (('airship_settings', 'airship_settings'), ('burrower', 'burrower_settings')):
            try:
                st = mb_cdo(cls)
                for n, v in (self.orig.get(key) or {}).items():
                    st.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
            except Exception:  # noqa: BLE001
                self.err('restore_' + key)
        for n, v in (self.orig.get('cvars') or {}).items():
            try:
                if v is not None:
                    mb_editor_cmd('%s %d' % (n, v))
            except Exception:  # noqa: BLE001
                self.err('restore_cvar')
        try:
            if 'engine' in self.orig:
                eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
                tl_set(eng, {'bUseFixedFrameRate': bool(self.orig['engine'].get('bUseFixedFrameRate', False)),
                             'FixedFrameRate': float(self.orig['engine'].get('FixedFrameRate', 30.0))})
        except Exception:  # noqa: BLE001
            self.err('restore_engine')

    # ------------------------------------------------------------------------------------------------- temp actors
    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            n = 0
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(self.TEMP):
                    eas.destroy_actor(a)
                    n += 1
            self.line('INFO', 'removed %d %s* actors from the editor level' % (n, self.TEMP))
        except Exception:  # noqa: BLE001
            self.err('remove_temp')

    def place_capture(self):
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, -100000))
        cap.set_actor_label(self.TEMP + 'Capture')
        cc = cap.capture_component2d
        cc.set_editor_property('capture_every_frame', False)
        cc.set_editor_property('capture_on_movement', False)
        return cap

    def place_block(self, label, scale, park):
        """a movable BlockAll cube (100 cm base) parked far away; the PIE copy is moved onto the lane by the test"""
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        b = eas.spawn_actor_from_object(unreal.load_asset('/Engine/BasicShapes/Cube'), unreal.Vector(*park), unreal.Rotator(0, 0, 0))
        b.set_actor_label(self.TEMP + label)
        b.set_actor_scale3d(unreal.Vector(*scale))
        smc = b.static_mesh_component
        smc.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
        smc.set_collision_profile_name('BlockAll')
        return b

    def pie_temp(self, w, label):
        for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Actor):
            try:
                if a.get_actor_label().endswith(self.TEMP + label) or a.get_actor_label() == self.TEMP + label:
                    return a
            except Exception:  # noqa: BLE001
                continue
        return None

    # ------------------------------------------------------------------------------------------------- log tail
    def log_poll(self):
        """new editor log lines since the last frame: kept ones get this frame's game time; match events parsed"""
        if not self.log_file:
            return
        try:
            size = os.path.getsize(self.log_file)
            if size < self.log_pos:        # rotated
                self.log_pos = 0
            if size == self.log_pos:
                return
            with open(self.log_file, 'rb') as f:
                f.seek(self.log_pos)
                data = f.read(min(size - self.log_pos, 4 << 20))
            self.log_pos += len(data)
            txt = self.log_part + data.decode('utf-8', 'replace')
            lines = txt.split('\n')
            self.log_part = lines.pop()
            for l in lines:
                if 'Repeating last play command' in l:
                    self.user_play = True
                if not any(k in l for k in MB_LOG_KEEP):
                    continue
                self.logl.append((r(self.now, 3), l.rstrip()[:600]))
                m = MB_EVENT_RE.search(l)
                if m:
                    self.mevents.append({'t': r(self.now, 3), 'event': m.group(1), 'team': int(m.group(2)), 'value': int(m.group(3)),
                                         'role': (m.group(4) or '').lower(), 'world': (m.group(5) or '').strip(), 'test': self.test})
            if len(self.logl) > 20000:
                self.logl = self.logl[-15000:]
        except Exception:  # noqa: BLE001
            self.err('log_poll')

    def log_since(self, t0, *pats):
        """kept log lines since game time t0 that contain every pattern"""
        return [(t, l) for t, l in self.logl if t >= t0 - 1e-3 and all(p in l for p in pats)]

    def events_since(self, t0, name=None, team=None, role=None, fallback=True):
        """match events seen in the log since t0; with no event line for that name, the server's own line for it
        (role 'server-line', team from the line's team name when it has one)"""
        ev = [e for e in self.mevents if e['t'] >= t0 - 1e-3 and (name is None or e['event'] == name)
              and (team is None or e['team'] == team) and (role is None or not e['role'] or e['role'] == role)]
        if ev or not fallback or name not in MB_EVENT_FALLBACK:
            return ev
        a, b = MB_EVENT_FALLBACK[name]
        out = []
        for t, l in self.log_since(t0, a, b):
            tm = next((i for i, n in enumerate(MB_TEAM_NAMES) if n in l), None)
            m = re.search(r'team (\d+)', l)
            if tm is None and m:
                tm = int(m.group(1))
            if team is None or tm == team:
                out.append({'t': t, 'event': name, 'team': tm, 'value': None, 'role': 'server-line', 'world': '', 'line': l[-160:]})
        return out

    def scan_log(self):
        """whole-run log counts for the report"""
        if not self.log_file:
            return
        try:
            with open(self.log_file, 'rb') as f:
                f.seek(self.log_off)
                lines = f.read().decode('utf-8', 'replace').splitlines()
            pats = {'match': 'LogMatch', 'lane': 'LogLane', 'airship_warn': 'LogAirship: Warning', 'error': 'Error:',
                    'ensure': 'Ensure condition failed', 'accessed_none': 'Accessed None', 'not_recognized': 'Command not recognized',
                    'fall_death': 'fall death', 'user_play': 'Repeating last play command', 'full': 'That match is full'}
            sc = {}
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                if k == 'error':
                    hit = [l for l in hit if 'not allowed' not in l and 'LoadErrors' not in l]
                sc[k] = {'count': len(hit), 'sample': hit[:10] + (hit[-5:] if len(hit) > 15 else [])}
            self.R['log_scan'] = sc
            nr = [c for c in set(x.split()[0] for x in self.cmds_run) if any('Command not recognized' in l and c in l for l in lines)]
            self.R['commands_not_recognised'] = nr
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    # ------------------------------------------------------------------------------------------------- worlds
    def role(self, w):
        try:
            if unreal.SystemLibrary.is_standalone(w):
                return 'standalone'
            return 'server' if unreal.SystemLibrary.is_server(w) else 'client'
        except Exception:  # noqa: BLE001
            return '?'

    def pie_worlds(self, map_name):
        try:
            return [w for w in unreal.EditorLevelLibrary.get_pie_worlds(False) if map_name in w.get_path_name()]
        except Exception:  # noqa: BLE001
            self.err('pie_worlds')
            return []

    def wtime(self, w):
        return float(unreal.GameplayStatics.get_time_seconds(w))

    def stime(self, w):
        """server world time as this machine sees it (AGameStateBase::GetServerWorldTimeSeconds)"""
        try:
            return float(self.gs(w).get_server_world_time_seconds())
        except Exception:  # noqa: BLE001
            return None

    def cmd(self, w, c):
        unreal.SystemLibrary.execute_console_command(w, c)
        self.cmds_run.append(c)
        self.event('cmd', cmd=c, world=self.role(w))
        self.line('INFO', 'console (%s): %s' % (self.role(w), c))

    # ------------------------------------------------------------------------------------------------- match readers
    def gs(self, w):
        return unreal.GameplayStatics.get_game_state(w)

    def phase_of(self, w):
        try:
            return mb_nz(self.gs(w).get_match_phase(), MB_PHASE)
        except Exception:  # noqa: BLE001
            self.err('phase_of')
            return None

    def result_of(self, w):
        try:
            g = self.gs(w)
            return {'result': mb_nz(g.get_match_result(), MB_RESULT), 'winner': int(g.get_winning_team()),
                    'reason': mb_nz(g.get_end_reason(), MB_REASON), 'round': int(g.get_round_index()),
                    'expected': int(g.get_expected_players()), 'phase_end': float(g.get_phase_end_server_time()),
                    'match_end': float(g.get_match_end_server_time())}
        except Exception:  # noqa: BLE001
            self.err('result_of')
            return {}

    def player_states(self, w):
        try:
            return [p for p in (self.gs(w).get_editor_property('player_array') or []) if valid(p)]
        except Exception:  # noqa: BLE001
            self.err('player_states')
            return []

    def team_of(self, a):
        try:
            return int(unreal.MyTeamLibrary.get_team_id(a))
        except Exception:  # noqa: BLE001
            self.err('team_of')
            return None

    def ps_team(self, ps):
        try:
            return int(ps.get_team_id())
        except Exception:  # noqa: BLE001
            return None

    def ships(self, w, alive=False):
        try:
            out = [s for s in unreal.GameplayStatics.get_all_actors_of_class(w, mb_cls('ship')) if valid(s)]
            if alive:
                out = [s for s in out if not s.is_airship_dead()]
            return out
        except Exception:  # noqa: BLE001
            self.err('ships')
            return []

    def ship_team(self, s):
        try:
            return int(s.get_team_id())
        except Exception:  # noqa: BLE001
            return None

    def team_ship(self, w, team):
        """the living ship of a team on this machine (the newest one if several, e.g. right after a respawn)"""
        ss = [s for s in self.ships(w, alive=True) if self.ship_team(s) == team]
        return ss[-1] if ss else None

    def lane_comp(self, s):
        try:
            return s.get_component_by_class(mb_cls('lane'))
        except Exception:  # noqa: BLE001
            return None

    def lane_state(self, s):
        try:
            c = self.lane_comp(s)
            return mb_nz(c.get_lane_state(), MB_LANE) if c is not None else None
        except Exception:  # noqa: BLE001
            self.err('lane_state')
            return None

    def tele(self, s):
        try:
            t = mb_parse_export(s.get_flight_telemetry().export_text())
            for k, names in (('LaneState', MB_LANE), ('LaneClamp', MB_CLAMP), ('UnpilotedMode', MB_UNPILOTED)):
                if k in t:
                    t[k + 'Name'] = mb_nz(t[k], names)
            return t
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def protected(self, s):
        try:
            return bool(s.is_spawn_protected())
        except Exception:  # noqa: BLE001
            return None

    def ship_hp(self, s):
        try:
            return round(float(self.tele(s).get('Health')), 2)
        except Exception:  # noqa: BLE001
            return self.health(s)

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

    def hull(self, s):
        return s.get_editor_property('HullCollision')

    def dump(self, w, label='state', max_age=0.0):
        """Aura.Match.Dump <file> on that machine, parsed (cached for max_age game seconds)"""
        key = (mb_name(w), label)
        c = self.dump_cache.get(key)
        if c is not None and self.now - c[0] <= max_age:
            return c[1]
        p = os.path.join(self.OUTDIR, 'dump', '%s_%s_%s.json' % (self.TAG, self.role(w), label))
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            if os.path.exists(p):
                os.remove(p)
            unreal.SystemLibrary.execute_console_command(w, 'Aura.Match.Dump %s' % p)
            with open(p) as f:
                d = json.load(f)
            self.dump_cache[key] = (self.now, d)
            return d
        except Exception:  # noqa: BLE001
            self.dump_fail += 1
            if self.dump_fail <= 3:
                self.err('dump')
            return None

    def team_state(self, w, team, max_age=0.0):
        return mb_get(self.dump(w, 'state', max_age), 'teams', team)

    def lanes_of(self, d):
        """the dump's lane numbers in cm"""
        out = {'has_lanes': mb_get(d, 'has_lanes')}
        for k in ('lane_start_u', 'path_end_u', 'cruise_end_u'):
            v = mb_get(d, k + '_m')
            out[k] = None if v is None else float(v) * 100.0
        return out

    def dump_ship(self, d, ship):
        n = mb_name(ship)
        return next((x for x in (mb_get(d, 'ships') or []) if x.get('name') == n), None)

    def status_teams(self, w, timeout=1.5):
        """yield: Aura.Match.Status on that machine, then its team lines from the log -> [{team, active, players,
        lives_left, bonus_lives, ships_lost, lane_side, ship_health_pct, ship, lane_state, eliminated}] (None if no lines)"""
        t0 = self.now
        unreal.SystemLibrary.execute_console_command(w, 'Aura.Match.Status')
        got = {}
        t1 = self.now
        while self.now - t1 < timeout and len(got) < 2:
            for t, l in self.log_since(t0, 'LogMatch'):
                m = MB_STATUS_TEAM_RE.search(l)
                if m and m.group(1) not in got:
                    got[m.group(1)] = {'team': MB_TEAM_NAMES.index(m.group(1)), 'active': m.group(2) == 'active', 'players': int(m.group(3)),
                                       'lives_left': int(m.group(4)), 'bonus_lives': int(m.group(5)), 'ships_lost': int(m.group(6)),
                                       'lane_side': int(m.group(7)), 'ship_health_pct': int(m.group(8)),
                                       'ship': None if m.group(9) == 'none' else m.group(9), 'lane_state': m.group(10),
                                       'eliminated': 'ELIMINATED' in (m.group(11) or '')}
            if len(got) < 2:
                yield
        return [got[n] for n in MB_TEAM_NAMES if n in got] if len(got) == 2 else None

    def keep_dump(self, label, d):
        self.R['dumps'][label] = d

    # ------------------------------------------------------------------------------------------------- frame (u, v)
    def set_frame(self, origin, yaw, half_width, source):
        self.frame = {'O': list(origin), 'yaw': float(yaw), 'H': float(half_width), 'source': source}
        self.R['setup']['frame'] = self.frame
        self.line('INFO', 'lane frame from %s: origin %s yaw %.1f H %.0f cm' % (source, r(list(origin), 0), yaw, half_width))

    def uv(self, p):
        """(u, v, z) of a world point in the start-heading frame (0.3)"""
        O, a = self.frame['O'], math.radians(self.frame['yaw'])
        dx, dy = p[0] - O[0], p[1] - O[1]
        return [dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a), p[2] - O[2]]

    def world(self, u, v, z):
        O, a = self.frame['O'], math.radians(self.frame['yaw'])
        return [O[0] + u * math.cos(a) - v * math.sin(a), O[1] + u * math.sin(a) + v * math.cos(a), O[2] + z]

    def lane_v(self, side):
        """the straight-path lane offset: side x (H + LaneClearance)"""
        return side * (self.frame['H'] + float(self.setting('LaneClearance', 2500.0)))

    def lane_point(self, side, u):
        return self.world(u, self.lane_v(side), float(self.setting('LaneHeight', 200.0)))

    # ------------------------------------------------------------------------------------------------- actors
    def loc(self, a):
        return v3(a.get_actor_location())

    def yaw(self, a):
        return float(a.get_actor_rotation().yaw)

    def teleport(self, s, loc, yaw=0.0, vel=(0.0, 0.0, 0.0)):
        s.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
        h = self.hull(s)
        h.set_physics_linear_velocity(unreal.Vector(*vel), False, 'None')
        h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')

    def wind_off(self, s):
        try:
            fc = s.get_editor_property('Flight')
            for n in ('WindLateralAccel', 'WindRollAccel', 'WindPitchAccel'):
                fc.set_editor_property(n, 0.0, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('wind_off')

    def set_scheme(self, s, scheme):
        try:
            s.set_control_scheme(getattr(unreal.AirshipControlScheme, {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}[int(scheme)]))
        except Exception:  # noqa: BLE001
            self.err('set_scheme')

    def hh(self, c):
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        return caps.get_scaled_capsule_half_height() if caps else 90.0

    def tp_char(self, c, loc, yaw=0.0):
        """an on-foot character to loc (feet + half height already in loc), stopped; attached characters are left alone"""
        try:
            if valid(c) and c.get_attach_parent_actor() is None:
                c.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
                cm = gp(c, 'character_movement', 'CharacterMovement')
                if cm:
                    cm.stop_movement_immediately()
                return True
        except Exception:  # noqa: BLE001
            self.err('tp_char')
        return False

    def deck_point(self, s, hx, hy, c=None):
        """world point on top of the hull at hull-space (hx, hy), plus the character's half height"""
        tr = s.get_actor_transform()
        top = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, 1600.0))
        bot = unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, -200.0))
        res = self.hull(s).line_trace_component(top, bot, False, False, False)
        hit = None
        if isinstance(res, tuple) and not (isinstance(res[0], bool) and not res[0]):
            hit = next((v3(x) for x in res if isinstance(x, unreal.Vector)), None)
        p = hit if hit is not None else v3(unreal.MathLibrary.transform_location(tr, unreal.Vector(hx, hy, 700.0)))
        return [p[0], p[1], p[2] + (self.hh(c) if c is not None else 90.0) + 30.0], hit is not None

    def base_owner(self, c):
        """the actor whose component the character stands on (None while falling)"""
        try:
            b = c.get_movement_base()
            return b.get_owner() if b is not None else None
        except Exception:  # noqa: BLE001
            return None

    def move_mode(self, c):
        try:
            return mb_nz(gp(c, 'character_movement', 'CharacterMovement').get_editor_property('movement_mode'))
        except Exception:  # noqa: BLE001
            return None

    def alive(self, c):
        h = self.health(c) if valid(c) else None
        return h is not None and h > 0.0

    def hull_gap(self, s, p):
        """3D distance from p to the hull collision (closest point), else to its bounds box"""
        try:
            res = self.hull(s).get_closest_point_on_collision(unreal.Vector(*p))
            d = res[0] if isinstance(res, tuple) else res
            if d is not None and float(d) >= 0.0:
                return float(d)
        except Exception:  # noqa: BLE001
            pass
        o, e = s.get_actor_bounds(True)
        q = [max(o.x - e.x, min(p[0], o.x + e.x)), max(o.y - e.y, min(p[1], o.y + e.y)), max(o.z - e.z, min(p[2], o.z + e.z))]
        return dist(p, q)

    def aabb_gap2d(self, a, b):
        """horizontal gap between the bounds boxes of two actors (0 when they overlap)"""
        oa, ea = a.get_actor_bounds(True)
        ob, eb = b.get_actor_bounds(True)
        gx = max(0.0, abs(oa.x - ob.x) - ea.x - eb.x)
        gy = max(0.0, abs(oa.y - ob.y) - ea.y - eb.y)
        return math.hypot(gx, gy)

    # ------------------------------------------------------------------------------------------------- platforms
    def platforms(self, w):
        out = []
        try:
            for p in unreal.GameplayStatics.get_all_actors_of_class(w, mb_cls('platform')):
                if not valid(p):
                    continue
                o, e = p.get_actor_bounds(True)
                if e.x <= 1.0 and e.y <= 1.0:
                    continue      # not generated yet
                c = self.uv([o.x, o.y, o.z])
                out.append({'a': p, 'u': c[0], 'v': c[1], 'vmin': c[1] - e.y, 'vmax': c[1] + e.y, 'umin': c[0] - e.x,
                            'umax': c[0] + e.x, 'ztop': o.z + e.z, 'zbot': o.z - e.z, 'sd': self.spline_d(p)})
        except Exception:  # noqa: BLE001
            self.err('platforms')
        return out

    def spline_d(self, p):
        try:
            return float(p.get_spline_distance())
        except Exception:  # noqa: BLE001
            return None

    def ground_at(self, w, x, y, z_top, z_bot, ignore=None):
        """first Visibility hit straight down at (x, y), or None"""
        try:
            res = unreal.SystemLibrary.line_trace_single(w, unreal.Vector(x, y, z_top + 500.0), unreal.Vector(x, y, z_bot - 200.0),
                                                         unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, ignore or [],
                                                         unreal.DrawDebugTrace.NONE, True)
            hit = res
            if isinstance(res, tuple):
                hit = next((x for x in res if isinstance(x, unreal.HitResult)), None)
            if hit is None:
                return None
            t = tuple(unreal.GameplayStatics.break_hit_result(hit))
            bools = [x for x in t if isinstance(x, bool)]
            vecs = [x for x in t if isinstance(x, unreal.Vector)]
            act = next((x for x in t if isinstance(x, unreal.Actor)), None)
            if not bools or not bools[0] or len(vecs) < 2:
                return None
            return {'p': v3(vecs[1]), 'actor': act}
        except Exception:  # noqa: BLE001
            self.err('ground_at')
            return None

    def platform_spot(self, w, u, side=None, edge=False, near_v=None, c=None):
        """a standing point (feet + half height) on a real platform near progress u. edge: on the platform reaching
        furthest toward side (the team's lane), as close to its outer edge as a downward trace finds the surface.
        near_v: the platform whose centre v is nearest. Returns (point, platform record) or (None, None)."""
        ps = [p for p in self.platforms(w) if abs(p['u'] - u) <= 6000.0]
        if not ps:
            ps = sorted(self.platforms(w), key=lambda p: abs(p['u'] - u))[:6]
        if not ps:
            return None, None
        if edge and side:
            ps.sort(key=lambda p: -(p['vmax'] if side > 0 else -p['vmin']))
        elif near_v is not None:
            ps.sort(key=lambda p: abs(p['v'] - near_v))
        else:
            ps.sort(key=lambda p: abs(p['u'] - u) + 0.3 * abs(p['v']))
        hh = self.hh(c) if c is not None else 90.0
        for p in ps[:5]:
            vs = [p['v']]
            if edge and side:
                ve = p['vmax'] if side > 0 else p['vmin']
                vs = [ve - side * d for d in (150.0, 350.0, 600.0, 900.0, 1300.0, 1800.0)] + vs
            for vv in vs:
                for uu in (min(max(u, p['umin'] + 200.0), p['umax'] - 200.0), p['u']):
                    q = self.world(uu, vv, 0.0)
                    g = self.ground_at(w, q[0], q[1], p['ztop'], p['zbot'])
                    if g is not None and (g['actor'] is None or mb_same(g['actor'], p['a']) or
                                          mb_same(getattr(g['actor'], 'get_attach_parent_actor', lambda: None)(), p['a'])):
                        return [g['p'][0], g['p'][1], g['p'][2] + hh + 20.0], p
        return None, None

    # ------------------------------------------------------------------------------------------------- input
    def subsystem(self, w):
        k = mb_name(w)
        s = self.subs.get(k)
        if s is not None and valid(s):
            return s
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and mb_same(lp.get_world(), w):
                    self.subs[k] = s
                    return s
            except Exception:  # noqa: BLE001
                pass
        return None

    def inject(self, w, action, vec=(1.0, 0.0, 0.0)):
        """one frame of input on that machine (held: every frame; a gap is the release)"""
        try:
            a = self.acts.get(action)
            if a is None:
                a = self.acts[action] = unreal.load_asset(MB_IA[action])
            self.subsystem(w).inject_input_vector_for_action(a, unreal.Vector(*vec), [], [])
        except Exception:  # noqa: BLE001
            self.err('inject_' + action)

    def cam(self, w):
        cm = unreal.GameplayStatics.get_player_camera_manager(w, 0)
        return cm.get_camera_location(), cm.get_camera_rotation()

    def aim(self, w, pc, point):
        """the view of that machine's local player at point (control rotation = look-at from the camera, plus the camera's
        lag behind it, capped at 15 deg: as_59's aim_at)"""
        try:
            loc, rot = self.cam(w)
            want = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(*point))
            ctrl = pc.get_control_rotation()
            ly = max(-15.0, min(15.0, wrap180(ctrl.yaw - rot.yaw)))
            lp = max(-15.0, min(15.0, wrap180(ctrl.pitch - rot.pitch)))
            pc.set_control_rotation(unreal.Rotator(0.0, wrap180(want.pitch + lp), wrap180(want.yaw + ly)))
            return r(wrap180(want.yaw - rot.yaw), 2), r(wrap180(want.pitch - rot.pitch), 2)
        except Exception:  # noqa: BLE001
            self.err('aim')
            return None

    # ------------------------------------------------------------------------------------------------- pictures
    def xgrab(self, label):
        """asks xgrab_loop.sh (started by the runner) to grab the editor's X window: the HUD is UMG, a scene capture
        doesn't draw it"""
        try:
            # one folder for every PR B harness: the runner's xgrab_loop.sh watches Saved/Match/xgrab
            d = os.path.join(MB_MATCH, 'xgrab')
            os.makedirs(d, exist_ok=True)
            lab = '%s_%s' % (os.path.basename(self.OUTDIR), label)
            with open(os.path.join(d, lab + '.req'), 'w') as f:
                f.write('%s %.2f\n' % (label, self.now))
            self.R['xgrabs'].append({'label': lab, 'file': os.path.join(d, 'x_%s_1.png' % lab), 't': r(self.now), 'test': self.test})
        except Exception:  # noqa: BLE001
            self.err('xgrab')

    def capture(self, w, label, frm, to, fov=60.0):
        """scene capture from the TEMP SceneCapture2D's PIE copy in that world; frm / to world points"""
        k = mb_name(w)
        if self.cap_dead.get(k) or self.ncap >= self.max_caps:
            return None
        try:
            if k not in self.cap:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.SceneCapture2D)
                        if (self.TEMP + 'Capture') in a.get_actor_label()]
                if not caps:
                    self.cap_dead[k] = True
                    self.line('WARN', 'no %sCapture in %s: no captures there' % (self.TEMP, k))
                    return None
                rt = unreal.RenderingLibrary.create_render_target2d(w, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = caps[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.cap[k] = (caps[0], cc, rt)
            a, cc, rt = self.cap[k]
            rot = unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*frm), unreal.Vector(*to))
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(unreal.Vector(*frm), rot, False, True)
            cc.capture_scene()
            d = os.path.join(self.OUTDIR, 'captures')
            os.makedirs(d, exist_ok=True)
            name = '%s_%s' % (self.TAG, label)
            unreal.RenderingLibrary.export_render_target(w, rt, d, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 't': r(self.now), 'file': os.path.join(d, name + '.png')})
            return name
        except Exception:  # noqa: BLE001
            self.err('capture')
            self.cap_dead[k] = True
            return None

    # ------------------------------------------------------------------------------------------------- test steps
    def wait(self, seconds):
        t0 = self.now
        while self.now - t0 < seconds:
            yield

    def until(self, cond, timeout):
        """yield frames until cond() is truthy (returns its value) or timeout game seconds (returns None)"""
        t0 = self.now
        while True:
            try:
                v = cond()
            except Exception:  # noqa: BLE001
                self.err('until_' + str(self.test))
                v = None
            if v:
                return v
            if self.now - t0 >= timeout:
                return None
            yield

    def say(self, msg):
        self.step = msg
        self.line('INFO', msg)

    # ------------------------------------------------------------------------------------------------- loop
    def run_tests(self):
        if self.gen is None:
            self.ti += 1
            if self.ti >= len(self.tests):
                self.finish('all tests done')
                return
            name, budget, fn = self.tests[self.ti]
            self.test, self.t_test0, self.D, self.step = name, self.now, {}, 'start'
            self.R['tests'].append([name, r(self.now)])
            self.line('INFO', 'test %s (at most %.0f game s)' % (name, budget))
            try:
                g = fn()
                self.gen = g if hasattr(g, 'send') else None
            except Exception:  # noqa: BLE001
                self.err('start_' + name)
                self.check(name + '_crash', 'FAIL', 'test crashed at its start: %s' % traceback.format_exc().strip().splitlines()[-1])
                self.gen = None
            self.write(True)
            return
        name, budget, _ = self.tests[self.ti]
        try:
            next(self.gen)
        except StopIteration:
            self.gen = None
            self.write(True)
            return
        except Exception:  # noqa: BLE001
            self.err('test_' + name)
            self.check(name + '_crash', 'FAIL', 'test crashed at step "%s": %s' % (self.step, traceback.format_exc().strip().splitlines()[-1]))
            self.gen = None
            self.write(True)
            return
        if self.now - self.t_test0 > budget:
            try:
                self.gen.close()
            except Exception:  # noqa: BLE001
                self.err('close_' + name)
            self.gen = None
            self.check(name + '_timeout', 'FAIL', 'test ran past its %.0f game s at step "%s"' % (budget, self.step))
            self.write(True)

    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if sum(e['n'] for e in self.R['errors'].values()) > 500:
                self.finish('too many script errors')
        self.write()

    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        try:
            if self.gen is not None:
                self.gen.close()
        except Exception:  # noqa: BLE001
            pass
        self.gen = None
        try:
            self.cleanup_pie()
        except Exception:  # noqa: BLE001
            self.err('cleanup_pie')
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
        self.report()
        self.line('INFO', 'done; results in %s' % self.path('report.txt'))

    def restore(self):
        self.restore_settings()

    # subclass hooks
    def cleanup_pie(self):
        pass

    def write_skips(self):
        for k, why in getattr(self, 'SKIPPED', {}).items():
            if k not in self.R['checks']:
                self.R['checks'][k] = {'status': 'SKIP', 'summary': why, 'data': None, 't': r(self.now), 'test': '-'}
        for name, _, _ in self.tests[self.ti + 1:] if self.ti >= 0 else self.tests:
            self.R['checks'].setdefault(name + '_not_run', {'status': 'SKIP', 'summary': 'not reached (%s)' % self.R.get('reason'),
                                                            'data': None, 't': r(self.now), 'test': '-'})
