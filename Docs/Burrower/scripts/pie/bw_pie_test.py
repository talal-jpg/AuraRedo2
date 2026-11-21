# bw_pie_test.py - Burrower PIE test for Docs/Burrower/EDITOR_SESSION.md step 8 (listen server + 1 client, StartupMap).
#
# Run it through the clone editor's inbox:  Docs/Burrower/scripts/harness/inbox.sh pie <this file> 120
# It checks the setup, places one TEMP_BW_Capture actor in the editor level, lowers the Burrower settings in memory,
# starts PIE and registers a Slate post-tick state machine, then returns at once (the world does not tick while an
# inbox script runs). Everything after that happens frame by frame in BwRun.tick(). Results:
#   <out_dir>/pie_result.json  (checks a..i with numbers, PASS/FAIL, events, errors; "done": true at the end)
#   <out_dir>/pie_log.txt      (one line per event / check, lines start with PASS:/FAIL:/WARN:/INFO:)
#   <out_dir>/pie_shots/<run_name>/*.png  (scene captures), <out_dir>/xgrab/*.req (X window grab requests)
# Read the result with bw_pie_report.py (plain python3, or through the inbox).
#
# Globals read before exec (all optional): BW_CONFIG (config JSON path), BW_PREFLIGHT_ONLY (True: checks only, no
# PIE, nothing changed), BW_NO_MAIN (True: only define the functions, for offline tests).
#
# Nothing is saved: no asset, no level, no config. In-memory changes (UBurrowerSettings CDO, LevelEditorPlaySettings,
# UnrealEdEngine fixed frame rate, CVar Aura.Burrower.DebugRotorBox) are restored when the run ends; the originals are
# also written to <out_dir>/pie_restore.json for bw_pie_cleanup.py. The TEMP_BW_ actor is removed after PIE ends.
#
# Engine facts this relies on (checked in UE 5.8 source / the clone's generated Python stub, see README.md):
#  * SystemLibrary.execute_console_command(world, cmd) runs cmd through IConsoleManager with that world
#    (KismetSystemLibrary.cpp:571-591), so Aura.Burrower.SpawnNow/KillAll (FAutoConsoleCommandWithWorld*) act on the
#    server world when it is passed.
#  * LevelEditorSubsystem.editor_request_begin_play() calls RequestPlaySession with the CDO play settings
#    (LevelEditorSubsystem.cpp:265-278); PlayNumberOfClients=2 + PIE_ListenServer = 1 listen server + 1 client
#    (PlayLevel.cpp:2887-2918).
#  * The user's own Play button goes through RepeatLastPlay, which logs "Repeating last play command"
#    (DebuggerCommands.cpp:1350); our start does not, so that line in the log means the user pressed Play.
#  * get/set_editor_property need CPF_Edit or BlueprintVisible (PropertyAccessUtil.cpp:425, 723); unexported classes
#    (UBurrowerSettings, LevelEditorPlaySettings) are reached with their C++ property names.
import json, os, time, math, traceback, glob, shutil

BW_SCRIPT_VERSION = 'bw_pie_test 2026-11-21'
BW_DEFAULT_CONFIG = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/pie/bw_pie_config.json'

# Defaults; the config JSON is merged over this (so it may be partial). README.md documents every key.
BW_DEFAULTS = {
    'run_name': 'pie_main',
    'map': '/Game/Maps/StartupMap',
    'expected_project_dir_contains': '_BurrowerWork',
    'out_dir': '/mnt/new_partition/UnrealProjects/_BurrowerWork/Saved/Burrower',
    'rig_info_json': '/mnt/new_partition/UnrealProjects/_BurrowerWork/SourceArt/Burrower/Burrower_rig_info.json',
    'player_bp_class': '/Game/Level/MechChar/BP_MyCharMech.BP_MyCharMech_C',
    'play': {'net_mode': 'PIE_ListenServer', 'num_clients': 2, 'run_under_one_process': True, 'force_in_memory': True},
    'fixed_frame_rate': 30.0,
    'settings': {'bEnabled': False, 'FirstSpawnDelay': 4.0, 'SpawnInterval': 8.0,
                 'burrower_class_if_unset': '/Game/Assets/Enemies/Burrower/BP_Burrower.BP_Burrower_C',
                 'allow_map_if_filtered': True},
    'spawn_mode': 'spawnnow',
    'spawn_indices': 'all',
    'enable_before_kill': True,
    'debug_rotor_box': True,
    'force_refresh_bones': True,
    'timeline': {'pie_start_timeout_wall_s': 180.0, 'pawn_timeout_s': 40.0, 'restart_missing_pawn_after_s': 3.0,
                 'warmup_s': 14.0, 'replication_wait_s': 1.5, 'auto_spawn_timeout_s': 20.0, 'follow_s': 16.0,
                 'cut_s': 12.0, 'damage_s': 8.0, 'ragdoll_s': 4.0, 'respawn_margin_s': 6.0,
                 'respawned_extra_s': 2.5, 'max_game_s': 300.0, 'max_wall_s': 2700.0, 'post_end_wall_s': 120.0},
    'move': {'speed': 900.0, 'follow_z': 500.0, 'ahead': 2500.0, 'cut_hover_z': 140.0, 'cut_ahead': 600.0,
             'braking_flying': 2000.0, 'hold_radius': 15.0, 'clear_radius': 120.0, 'lane_pitch': -12.0},
    'sampling': {'dist_dt': 0.5, 'pose_dt': 0.1, 'tile_dt': 0.5, 'health_dt': 0.25, 'summary_dt': 1.0,
                 'ragdoll_dt': 0.2, 'rotor_window_start': 6.0, 'rotor_window_s': 2.0, 'tile_track_radius': 6000.0,
                 'log_scan_wall_s': 2.0, 'write_wall_s': 1.0},
    'thresholds': {'spawn_dist_tol_frac': 0.1, 'spawn_z_tol_cm': 80.0, 'spawn_behind_dot_min': 0.9,
                   'client_pos_tol_cm': 400.0, 'follow_end_max_cm': 2500.0, 'follow_bound_extra_cm': 600.0,
                   'follow_min_travel_cm': 1000.0, 'wave_min_p2p_cm': 15.0, 'wave_min_crossings': 2,
                   'rotor_min_turn_deg': 90.0, 'rotor_loc_tol_cm': 3.0, 'rotor_axis_tol_deg': 3.0,
                   'rotor_alias_deg_per_sample': 150.0, 'pipe_anchor_tol_cm': 5.0, 'pipe_mid_min_std_cm': 0.5,
                   'tile_cut_extra_cm': 100.0, 'tiles_min_cut': 1, 'health_min_drop': 0.5,
                   'ragdoll_min_bone_move_cm': 30.0, 'ragdoll_max_actor_move_cm': 50.0, 'dead_wait_server_s': 1.0,
                   'dead_wait_client_s': 2.5, 'respawn_tol_early_s': 0.5, 'respawn_tol_late_s': 2.5},
    'damage': {'fire_roles': ['server'], 'aim_bone': 'J2_Midbody', 'input_action': '/Game/Level/PlayerInput/IA_LMB',
               'stop_after_drop': 3.0, 'fallback_ge': '/Game/Level/GAS/GameplayEffects/GE_GunShootDamage.GE_GunShootDamage_C',
               'fallback_damage': 5.0, 'set_by_caller_tag': 'SetDamageByCaller', 'fallback_wait_s': 2.0},
    'bones': {'body': ['J0_Head', 'J1_Forequarters', 'J2_Midbody', 'J3_Hindbody', 'J4_Tail'], 'rotor': 'Rotor',
              'pipe_anchor': 'J1_Forequarters', 'rotor_rest_cm': [977.9, 0.0, 180.5], 'j1_rest_cm': [660.0, 0.0, 193.0]},
    'shots': {'enabled': True, 'xgrab': True, 'width': 1280, 'height': 720, 'max_captures': 48, 'look_lead_s': 1.0,
              'plan': [
                  {'phase': 'spawn', 'at': 1.0, 'label': 'a_spawn', 'kinds': ['side', 'player']},
                  {'phase': 'follow', 'at': 7.0, 'label': 'd_rotor', 'kinds': ['rotor']},
                  {'phase': 'follow', 'at': 10.0, 'label': 'bcf_follow', 'kinds': ['side', 'player']},
                  {'phase': 'cut', 'at': 6.0, 'label': 'e_cut', 'kinds': ['top', 'player']},
                  {'phase': 'cut', 'at': 11.0, 'label': 'e_cut_end', 'kinds': ['top']},
                  {'phase': 'damage', 'at': 4.0, 'label': 'g_damage', 'kinds': ['player', 'side']},
                  {'phase': 'kill', 'at': 1.5, 'label': 'h_ragdoll', 'kinds': ['side', 'player']},
                  {'phase': 'kill', 'at': 3.5, 'label': 'h_ragdoll2', 'kinds': ['side']},
                  {'phase': 'respawned', 'at': 1.5, 'label': 'i_respawn', 'kinds': ['side', 'player']}]},
}

BW_CHECK_ORDER = ['setup', 'a_spawn', 'b_follow', 'c_wave', 'd_rotor', 'e_tiles', 'f_pipes', 'g_damage', 'h_death',
                  'i_respawn']
BW_TEMP_LABEL = 'TEMP_BW_Capture'
BW_SETTINGS_CLASS = '/Script/Aura.BurrowerSettings'
BW_SETTINGS_KEYS = ['bEnabled', 'FirstSpawnDelay', 'SpawnInterval', 'PlayerRespawnGrace', 'SpawnDistanceBehind',
                    'SpawnHeightOffset', 'MinSpeedForVelocityDirection', 'MaxAlivePerPlayer', 'bRespawnAfterDeath',
                    'DespawnDistance', 'bOnlyCombatPawns', 'PollInterval', 'AllowedMaps']


# =====================================================================================================================
# Small helpers (pure Python, testable offline)
# =====================================================================================================================

def bw_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = bw_merge(out[k], v)
        else:
            out[k] = v
    return out


def bw_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def bw_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def bw_mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def bw_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def bw_len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def bw_len2d(a):
    return math.hypot(a[0], a[1])


def bw_norm(a):
    n = bw_len(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else (0.0, 0.0, 0.0)


def bw_r(v, n=1):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(v, n)
    return [round(x, n) for x in v]


def bw_qmul(a, b):
    """Hamilton product a*b of quaternions (x, y, z, w), the same convention as FQuat::operator*."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def bw_qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def bw_qrot(q, v):
    """Rotates vector v by unit quaternion q."""
    r = bw_qmul(bw_qmul(q, (v[0], v[1], v[2], 0.0)), bw_qconj(q))
    return (r[0], r[1], r[2])


def bw_wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def bw_twist_swing_x(q):
    """Twist about +X (deg, -180..180) and the remaining swing angle (deg) of rotation q (x, y, z, w)."""
    x, y, z, w = q
    n = math.hypot(x, w)
    if n < 1e-9:
        return 180.0, 180.0
    tq = (x / n, 0.0, 0.0, w / n)
    twist = math.degrees(2.0 * math.atan2(tq[0], tq[3]))
    s = bw_qmul(q, bw_qconj(tq))
    swing = math.degrees(2.0 * math.acos(min(1.0, abs(s[3]))))
    return bw_wrap180(twist), swing


def bw_osc_stats(vals):
    """Oscillation stats of a series: peak to peak, std, mean crossings with 20 % hysteresis."""
    vals = [v for v in vals if v is not None]
    if len(vals) < 5:
        return None
    mean = sum(vals) / len(vals)
    p2p = max(vals) - min(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
    hyst = 0.1 * p2p
    state = 0
    crossings = 0
    for v in vals:
        d = v - mean
        if d > hyst:
            s = 1
        elif d < -hyst:
            s = -1
        else:
            continue
        if state != 0 and s != state:
            crossings += 1
        state = s
    return {'n': len(vals), 'mean': round(mean, 2), 'p2p': round(p2p, 2), 'std': round(std, 2), 'crossings': crossings}


def bw_lag(a, b, max_lag):
    """Lag (samples) of series b behind a with the best correlation; > 0 = b follows a."""
    n = min(len(a), len(b))
    if n < 10:
        return None
    a = a[:n]
    b = b[:n]
    ma = sum(a) / n
    mb = sum(b) / n
    best = None
    for lag in range(-max_lag, max_lag + 1):
        s = 0.0
        cnt = 0
        for i in range(n):
            j = i + lag
            if 0 <= j < n:
                s += (a[i] - ma) * (b[j] - mb)
                cnt += 1
        if cnt > n // 2:
            c = s / cnt
            if best is None or c > best[1]:
                best = (lag, c)
    return best[0] if best else None


class BwStat(object):
    """Running mean / std of 3D points (Welford)."""

    def __init__(self):
        self.n = 0
        self.mean = [0.0, 0.0, 0.0]
        self.m2 = [0.0, 0.0, 0.0]

    def add(self, p):
        self.n += 1
        for i in range(3):
            d = p[i] - self.mean[i]
            self.mean[i] += d / self.n
            self.m2[i] += d * (p[i] - self.mean[i])

    def std(self):
        if self.n < 2:
            return 0.0
        return math.sqrt(sum(self.m2) / self.n)


def bw_status_word(s):
    return {'PASS': 'PASS', 'FAIL': 'FAIL', 'WARN': 'WARN', 'SKIP': 'WARN'}.get(s, 'INFO')


# =====================================================================================================================
# Unreal helpers
# =====================================================================================================================

def bw_vec(v):
    return (float(v.x), float(v.y), float(v.z))


def bw_quat(q):
    return (float(q.x), float(q.y), float(q.z), float(q.w))


def bw_uvec(t):
    return unreal.Vector(float(t[0]), float(t[1]), float(t[2]))


def bw_get(obj, *names, **kw):
    for n in names:
        try:
            return obj.get_editor_property(n)
        except Exception:
            continue
    return kw.get('default')


def bw_set(obj, name, value):
    """set_editor_property without PostEditChange (no re-registration of PIE components, no settings save)."""
    obj.set_editor_property(name, value, unreal.PropertyAccessChangeNotifyMode.NEVER)


def bw_valid(a):
    try:
        return a is not None and unreal.SystemLibrary.is_valid(a)
    except Exception:
        return False


def bw_role(w):
    try:
        if unreal.SystemLibrary.is_standalone(w):
            return 'standalone'
        return 'server' if unreal.SystemLibrary.is_server(w) else 'client'
    except Exception:
        return '?'


def bw_rts_component():
    try:
        return unreal.RelativeTransformSpace.RTS_COMPONENT
    except Exception:
        return None


def bw_burrower_class():
    c = getattr(unreal, 'BurrowerCharacter', None)
    if c is None:
        c = unreal.load_class(None, '/Script/Aura.BurrowerCharacter')
    return c


def bw_obj_types():
    ot = unreal.ObjectTypeQuery
    st = getattr(ot, 'ECC_WORLD_STATIC', None) or getattr(ot, 'OBJECT_TYPE_QUERY1')
    dy = getattr(ot, 'ECC_WORLD_DYNAMIC', None) or getattr(ot, 'OBJECT_TYPE_QUERY2')
    return [st, dy]


def bw_engine():
    return unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')


def bw_play_settings():
    return unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))


def bw_settings_cdo():
    cls = unreal.load_class(None, BW_SETTINGS_CLASS)
    return unreal.get_default_object(cls) if cls else None


def bw_tl_get(obj, names):
    return json.loads(unreal.ToolsetLibrary.get_object_properties(obj, names))


def bw_tl_set(obj, values):
    return unreal.ToolsetLibrary.set_object_properties(obj, json.dumps(values))


def bw_class_path(c):
    try:
        return c.get_path_name() if c is not None else None
    except Exception:
        return str(c)


def bw_read_settings(cdo):
    out = {}
    for k in BW_SETTINGS_KEYS:
        try:
            v = cdo.get_editor_property(k)
            if k == 'AllowedMaps':
                v = [str(x) for x in v]
            out[k] = v
        except Exception as e:
            out[k] = 'ERROR %r' % e
    try:
        out['BurrowerClass'] = bw_class_path(cdo.get_editor_property('BurrowerClass'))
    except Exception as e:
        out['BurrowerClass'] = 'ERROR %r' % e
    return out


def bw_restore_settings(cdo, orig):
    """Puts the UBurrowerSettings CDO values back (in memory, never saved)."""
    done = []
    for k, v in orig.items():
        if isinstance(v, str) and v.startswith('ERROR'):
            continue
        try:
            if k == 'BurrowerClass':
                cls = unreal.load_class(None, v) if v else None
                bw_set(cdo, 'BurrowerClass', cls)
            elif k == 'AllowedMaps':
                bw_set(cdo, 'AllowedMaps', list(v))
            else:
                bw_set(cdo, k, v)
            done.append(k)
        except Exception as e:
            done.append('%s FAILED %r' % (k, e))
    return done


def bw_local_pc(w):
    try:
        pc = unreal.GameplayStatics.get_player_controller(w, 0)
        if pc and pc.is_local_controller():
            return pc
    except Exception:
        pass
    return None


def bw_pid_of_pawn(p):
    try:
        ps = bw_get(p, 'player_state')
        if ps is None:
            return None
        return int(bw_get(ps, 'player_id', 'PlayerId'))
    except Exception:
        return None


def bw_ism_tiles(ism):
    """{(round(x/10), round(y/10)): (x, y, z)} of every instance (world space, z = pillar top)."""
    out = {}
    try:
        n = ism.get_instance_count()
    except Exception:
        return None
    for i in range(n):
        try:
            r = ism.get_instance_transform(i, True)
        except Exception:
            continue
        xf = r[1] if isinstance(r, tuple) else r
        if xf is None:
            continue
        p = bw_vec(xf.translation)
        out[(int(round(p[0] / 10.0)), int(round(p[1] / 10.0)))] = p
    return out


def bw_near_tile(tiles, pos, tol):
    """True if a tile of tiles ({key: (x, y, z)}) lies within tol cm (horizontal) of pos."""
    kx, ky = int(round(pos[0] / 10.0)), int(round(pos[1] / 10.0))
    r = int(math.ceil(tol / 10.0))
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            q = tiles.get((kx + dx, ky + dy))
            if q is not None and math.hypot(q[0] - pos[0], q[1] - pos[1]) <= tol:
                return True
    return False


def bw_match_actor(actors, loc, tol):
    """The actor of {key: actor} whose location is nearest to loc, within tol cm (replicated locations may be quantized)."""
    best = None
    for a in actors.values():
        try:
            d = bw_len(bw_sub(bw_vec(a.get_actor_location()), loc))
        except Exception:
            continue
        if d <= tol and (best is None or d < best[0]):
            best = (d, a)
    return best[1] if best else None


def bw_meminfo_gb():
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return round(int(line.split()[1]) / 1048576.0, 1)
    except Exception:
        pass
    return None


def bw_find_log():
    try:
        d = os.path.abspath(unreal.Paths.project_log_dir())
    except Exception:
        return None
    p = os.path.join(d, 'Aura.log')
    if os.path.isfile(p):
        return p
    logs = [x for x in glob.glob(os.path.join(d, '*.log')) if 'backup' not in os.path.basename(x)]
    return max(logs, key=os.path.getmtime) if logs else None


# =====================================================================================================================
# The run
# =====================================================================================================================

class BwRun(object):

    def __init__(self, cfg):
        self.cfg = cfg
        self.T = cfg['timeline']
        self.M = cfg['move']
        self.S = cfg['sampling']
        self.TH = cfg['thresholds']
        self.D = cfg['damage']
        self.B = cfg['bones']
        self.out_dir = cfg['out_dir']
        self.result_path = os.path.join(self.out_dir, 'pie_result.json')
        self.log_path = os.path.join(self.out_dir, 'pie_log.txt')
        self.restore_path = os.path.join(self.out_dir, 'pie_restore.json')
        self.shot_dir = os.path.join(self.out_dir, 'pie_shots', cfg['run_name'])
        self.xgrab_dir = os.path.join(self.out_dir, 'xgrab')
        self.R = {'script': BW_SCRIPT_VERSION, 'run_name': cfg['run_name'], 'config': cfg, 'armed_wall': time.time(),
                  'armed_utc': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()), 'done': False, 'reason': None,
                  'phase': 'arming', 'checks': {}, 'events': [], 'errors': [], 'samples': [], 'shots': [],
                  'restore': {}, 'log_scan': {}, 'series': {}, 'players': {}, 'preflight': []}
        self.done = False
        self.ended = False
        self.handle = None
        self.phase = 'arming'
        self.phase_t0 = 0.0
        self.now = 0.0
        self.started = False
        self.session_real = None
        self.last_write = 0.0
        self.last_log_scan = 0.0
        self.log_file = None
        self.log_offset = 0
        self.user_play = False
        self.err_count = 0
        self.captures = 0
        self.cap_res = {}
        self.cap_dead = set()
        self.shot_done = set()
        self.orig = {}
        self.bcls = None
        self.ia = None
        self.health_attr = None
        self.maxhealth_attr = None
        self.rts_comp = None
        self.rig = None
        self.paths = []
        self.players = {}          # pid -> {'lane', 'hold', 'hover', 'first_pawn_t'}
        self.flying = set()
        self.burrowers = {'server': {}, 'client': {}}   # role -> path -> rec
        self.rotor_hist = {'server': [], 'client': []}
        self.platforms = {'server': {}, 'client': {}}   # role -> key -> rec
        self.platform_list_t = {'server': -99.0, 'client': -99.0}
        self.platform_actors = {'server': {}, 'client': {}}
        self.next = {}
        self.wall_last = None
        self.game_last = None
        self.fps = None
        self.spawn = {}
        self.kill = {}
        self.respawn = {}
        self.damage = {}
        self.tile_eval_pending = False
        self.missing_restarted = set()
        self.ws = []
        self.sw = None
        self.cw = None

    # ------------------------------------------------------------------ output

    def line(self, level, msg):
        txt = '%s: %s' % (level, msg)
        stamp = '[%s g=%.1f %s]' % (time.strftime('%H:%M:%S'), self.now, self.phase)
        try:
            with open(self.log_path, 'a') as f:
                f.write(stamp + ' ' + txt + '\n')
        except Exception:
            pass
        if self.phase in ('arming', 'preflight'):
            print(txt)
        return txt

    def event(self, kind, **data):
        e = {'t': round(self.now, 2), 'phase': self.phase, 'kind': kind}
        e.update(data)
        if len(self.R['events']) < 600:
            self.R['events'].append(e)
        return e

    def err(self, where):
        self.err_count += 1
        if len(self.R['errors']) < 80:
            self.R['errors'].append('g=%.2f %s %s: %s' % (self.now, self.phase, where, traceback.format_exc()[-700:]))

    def check(self, key, status, summary, data=None):
        self.R['checks'][key] = {'status': status, 'summary': summary, 'data': data or {}, 't': round(self.now, 2)}
        self.line(bw_status_word(status), '%s %s' % (key, summary))
        self.write(force=True)

    def write(self, force=False):
        if not force and time.time() - self.last_write < self.S['write_wall_s']:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = round(self.now, 2)
        self.R['fps_est'] = self.fps
        try:
            os.makedirs(self.out_dir, exist_ok=True)
            with open(self.result_path + '.tmp', 'w') as f:
                json.dump(self.R, f, default=str, indent=1)
            os.replace(self.result_path + '.tmp', self.result_path)
        except Exception:
            pass

    # ------------------------------------------------------------------ arming

    def preflight(self, arm):
        """Read-only checks. Returns False when the run must not start. With arm=True it also changes the in-memory
        settings it needs (recorded in self.orig)."""
        P = self.R['preflight']
        ok = True

        def note(level, msg):
            P.append(self.line(level, msg))

        os.makedirs(self.out_dir, exist_ok=True)
        # project and PIE
        try:
            pdir = os.path.abspath(unreal.Paths.project_dir())
        except Exception:
            pdir = '?'
        if self.cfg['expected_project_dir_contains'] not in pdir:
            note('FAIL', 'the editor runs project %s, not the Burrower clone (%s); refusing to run' % (pdir, self.cfg['expected_project_dir_contains']))
            return False
        note('INFO', 'project %s' % pdir)
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            note('FAIL', 'PIE is already running (maybe the user plays): stop it first, then arm again')
            return False
        try:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            wpath = ew.get_path_name() if ew else '?'
        except Exception:
            wpath = '?'
        mapname = self.cfg['map'].split('/')[-1]
        if not wpath.startswith(self.cfg['map'] + '.'):
            note('FAIL', 'the editor world is %s, not %s: relaunch with harness/launch.sh %s' % (wpath, self.cfg['map'], self.cfg['map']))
            ok = False
        else:
            note('PASS', 'editor map %s' % wpath)
        # C++ classes
        try:
            self.bcls = bw_burrower_class()
            note('PASS' if self.bcls else 'FAIL', 'class BurrowerCharacter %s' % ('found' if self.bcls else 'missing (C++ not built?)'))
            ok = ok and bool(self.bcls)
        except Exception as e:
            note('FAIL', 'BurrowerCharacter class: %r (build AuraEditor first)' % e)
            ok = False
        try:
            self.rts_comp = bw_rts_component()
            if self.rts_comp is None:
                note('WARN', 'unreal.RelativeTransformSpace missing: component space is computed from world space')
        except Exception:
            pass
        # settings
        cdo = None
        try:
            cdo = bw_settings_cdo()
        except Exception as e:
            note('FAIL', 'UBurrowerSettings CDO: %r' % e)
        if cdo is None:
            note('FAIL', 'UBurrowerSettings not found (/Script/Aura.BurrowerSettings)')
            return False
        sett = bw_read_settings(cdo)
        self.R['settings_before'] = sett
        note('INFO', 'BurrowerSettings %s' % json.dumps(sett, default=str))
        cls_path = sett.get('BurrowerClass')
        use_cls = None
        if not cls_path or str(cls_path).startswith('ERROR'):
            alt = self.cfg['settings'].get('burrower_class_if_unset')
            try:
                use_cls = unreal.load_class(None, alt) if alt else None
            except Exception:
                use_cls = None
            if use_cls:
                note('WARN', 'Burrower Class is not set in Project Settings > Game > Burrower (EDITOR_SESSION step 7); this run sets it in memory to %s' % alt)
            else:
                note('FAIL', 'Burrower Class is not set and %s does not load: create BP_Burrower first (step 6/7)' % alt)
                ok = False
        else:
            try:
                use_cls = unreal.load_class(None, cls_path)
            except Exception:
                use_cls = None
            note('PASS' if use_cls else 'FAIL', 'Burrower Class %s %s' % (cls_path, 'loads' if use_cls else 'does not load'))
            ok = ok and bool(use_cls)
        # BP_Burrower defaults
        if use_cls:
            try:
                bcdo = unreal.get_default_object(use_cls)
                mesh = bw_get(bcdo, 'mesh')
                sk = None
                anim = None
                try:
                    sk = mesh.get_skeletal_mesh_asset()
                except Exception:
                    sk = bw_get(mesh, 'skeletal_mesh_asset')
                anim = bw_get(mesh, 'anim_class')
                info = {'mesh': bw_class_path(sk), 'anim_class': bw_class_path(anim),
                        'use_mesh_ragdoll_fallback': bw_get(bcdo, 'use_mesh_ragdoll_fallback'),
                        'refresh_bones_on_server': bw_get(bcdo, 'refresh_bones_on_server'),
                        'rotor_spin_speed': bw_get(bcdo, 'rotor_spin_speed'), 'life_span': bw_get(bcdo, 'life_span'),
                        'character_class': str(bw_get(bcdo, 'character_class'))}
                try:
                    hbc = bw_get(bcdo, 'health_bar_widget_component')
                    try:
                        wc = hbc.get_widget_class() if hbc else None
                    except Exception:
                        wc = bw_get(hbc, 'widget_class')
                    info['health_bar_widget'] = bw_class_path(wc)
                except Exception:
                    info['health_bar_widget'] = '?'
                self.R['burrower_bp'] = info
                note('PASS' if sk else 'FAIL', 'BP_Burrower mesh %s' % info['mesh'])
                note('PASS' if anim else 'WARN', 'BP_Burrower anim class %s%s' % (info['anim_class'], '' if anim else ' (no ABP: wave/rotor/pipes checks will fail)'))
                note('INFO', 'BP_Burrower defaults %s' % json.dumps(info, default=str))
                ok = ok and bool(sk)
            except Exception as e:
                note('WARN', 'could not read the BP_Burrower defaults: %r' % e)
        # GameMode class info (spawns need it)
        try:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            gm_cls = bw_get(ew.get_world_settings(), 'default_game_mode')
            gm_cdo = unreal.get_default_object(gm_cls) if gm_cls else None
            dai = bw_get(gm_cdo, 'da_my_enemy_character_class_info', 'DA_MyEnemyCharacterClassInfo') if gm_cdo else None
            if gm_cls is None:
                note('INFO', 'the map has no GameMode override (the project default is used); the class info is checked again in PIE')
            else:
                note('PASS' if dai else 'WARN', 'map GameMode %s, DA_MyEnemyCharacterClassInfo %s%s' % (bw_class_path(gm_cls), bw_class_path(dai), '' if dai else ' (spawns are refused without it)'))
        except Exception as e:
            note('WARN', 'could not read the map GameMode: %r' % e)
        # player BP debug death
        try:
            pcls = unreal.load_class(None, self.cfg['player_bp_class'])
            dd = bw_get(unreal.get_default_object(pcls), 'debug_die_after_begin_play_seconds', 'DebugDieAfterBeginPlaySeconds')
            note('PASS' if not dd else 'WARN', '%s DebugDieAfterBeginPlaySeconds = %s%s' % (self.cfg['player_bp_class'], dd, '' if not dd else ' (players die after that many seconds: the spawner pauses; set it to 0 in BP_MyCharMech)'))
        except Exception as e:
            note('WARN', 'could not read the player BP: %r' % e)
        # assets the test uses
        try:
            self.ia = unreal.load_asset(self.D['input_action'])
            note('PASS' if self.ia else 'WARN', 'input action %s %s' % (self.D['input_action'], 'loads' if self.ia else 'missing (no gunfire, GE fallback only)'))
        except Exception as e:
            note('WARN', 'input action: %r' % e)
        try:
            ge = unreal.load_class(None, self.D['fallback_ge'])
            note('PASS' if ge else 'WARN', 'fallback damage GE %s %s' % (self.D['fallback_ge'], 'loads' if ge else 'missing'))
        except Exception as e:
            note('WARN', 'fallback GE: %r' % e)
        try:
            self.health_attr = unreal.GameplayAttribute()
            self.health_attr.import_text('(AttributeName="Health",Attribute=/Script/Aura.MyAttributeSet:Health,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")')
            self.maxhealth_attr = unreal.GameplayAttribute()
            self.maxhealth_attr.import_text('(AttributeName="MaxHealth",Attribute=/Script/Aura.MyAttributeSet:MaxHealth,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")')
        except Exception as e:
            note('WARN', 'GameplayAttribute import: %r' % e)
        # rig info
        try:
            with open(self.cfg['rig_info_json']) as f:
                self.rig = json.load(f)
            note('PASS', 'rig info: %d pipe chains' % len(self.rig.get('chains', [])))
        except Exception as e:
            self.rig = {'chains': []}
            note('WARN', 'rig info %s not readable (%r): pipe check skipped' % (self.cfg['rig_info_json'], e))
        # play settings
        try:
            ps = bw_tl_get(bw_play_settings(), ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
            self.R['play_settings_before'] = ps
            want = self.cfg['play']
            good = (str(ps.get('PlayNetMode')).endswith(want['net_mode']) and int(ps.get('PlayNumberOfClients', 0)) == int(want['num_clients'])
                    and bool(ps.get('RunUnderOneProcess')) == bool(want['run_under_one_process']))
            note('PASS' if good else 'WARN', 'play settings %s%s' % (ps, '' if good else ' (expected %s/%s/%s: run bw_ini_playmode.sh set with the editor closed%s)' % (
                want['net_mode'], want['num_clients'], want['run_under_one_process'], '; this run sets them in memory' if want['force_in_memory'] else '')))
        except Exception as e:
            note('WARN', 'play settings unreadable: %r' % e)
        # engine, memory, level, log
        try:
            self.R['engine_before'] = bw_tl_get(bw_engine(), ['bUseFixedFrameRate', 'FixedFrameRate'])
        except Exception as e:
            note('WARN', 'UnrealEdEngine_0 fixed frame rate unreadable: %r' % e)
        mem = bw_meminfo_gb()
        note('PASS' if (mem is None or mem >= 3.0) else 'WARN', 'MemAvailable %s GB%s' % (mem, '' if (mem is None or mem >= 3.0) else ' (low: the PC froze before at < 3 GB)'))
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            temps = [a.get_actor_label() for a in eas.get_all_level_actors() if 'TEMP_' in a.get_actor_label()]
            note('INFO' if not temps else 'WARN', 'TEMP_ actors in the level: %s' % temps)
        except Exception as e:
            note('WARN', 'level actors: %r' % e)
        self.log_file = bw_find_log()
        note('PASS' if self.log_file else 'WARN', 'editor log %s' % self.log_file)
        if not arm or not ok:
            return ok

        # ---- in-memory changes (recorded for the restore)
        self.orig = {'settings': sett, 'armed_wall': time.time(), 'log_file': self.log_file}
        try:
            changes = {}
            for k in ('bEnabled', 'FirstSpawnDelay', 'SpawnInterval'):
                if k in self.cfg['settings']:
                    bw_set(cdo, k, self.cfg['settings'][k])
                    changes[k] = self.cfg['settings'][k]
            if (not cls_path or str(cls_path).startswith('ERROR')) and use_cls:
                bw_set(cdo, 'BurrowerClass', use_cls)
                changes['BurrowerClass'] = bw_class_path(use_cls)
            amaps = sett.get('AllowedMaps') or []
            if amaps and isinstance(amaps, list) and mapname not in amaps and self.cfg['settings'].get('allow_map_if_filtered'):
                bw_set(cdo, 'AllowedMaps', list(amaps) + [mapname])
                changes['AllowedMaps'] = list(amaps) + [mapname]
            self.R['settings_changes'] = changes
            self.R['settings_during'] = bw_read_settings(cdo)
            note('INFO', 'BurrowerSettings (memory only) %s' % json.dumps(changes, default=str))
        except Exception as e:
            note('FAIL', 'could not change UBurrowerSettings in memory: %r' % e)
            return False
        try:
            want = self.cfg['play']
            if want.get('force_in_memory'):
                self.orig['play'] = self.R.get('play_settings_before')
                bw_tl_set(bw_play_settings(), {'PlayNetMode': want['net_mode'], 'PlayNumberOfClients': int(want['num_clients']),
                                               'RunUnderOneProcess': bool(want['run_under_one_process'])})
                self.R['play_settings_during'] = bw_tl_get(bw_play_settings(), ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
                note('INFO', 'play settings in memory %s' % self.R['play_settings_during'])
        except Exception as e:
            note('WARN', 'could not set the play settings in memory: %r' % e)
        try:
            self.orig['engine'] = self.R.get('engine_before')
            if self.cfg.get('fixed_frame_rate'):
                bw_tl_set(bw_engine(), {'bUseFixedFrameRate': True, 'FixedFrameRate': float(self.cfg['fixed_frame_rate'])})
                note('INFO', 'fixed frame rate %s (game time locked even when the editor is on a hidden workspace)' % self.cfg['fixed_frame_rate'])
        except Exception as e:
            note('WARN', 'could not set the fixed frame rate: %r' % e)
        try:
            self.orig['cvar_debug_rotor_box'] = unreal.SystemLibrary.get_console_variable_int_value('Aura.Burrower.DebugRotorBox')
        except Exception:
            self.orig['cvar_debug_rotor_box'] = 0
        if self.log_file:
            try:
                self.log_offset = os.path.getsize(self.log_file)
            except Exception:
                self.log_offset = 0
        self.orig['log_offset'] = self.log_offset
        try:
            with open(self.restore_path, 'w') as f:
                json.dump(self.orig, f, default=str, indent=1)
        except Exception as e:
            note('WARN', 'could not write %s: %r' % (self.restore_path, e))
        # TEMP capture actor (copied into both PIE worlds; removed after PIE)
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith('TEMP_BW_'):
                    eas.destroy_actor(a)
            if self.cfg['shots']['enabled']:
                cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, -3000, 400))
                cap.set_actor_label(BW_TEMP_LABEL)
                cap.capture_component2d.set_editor_property('capture_every_frame', False)
                cap.capture_component2d.set_editor_property('capture_on_movement', False)
                note('INFO', 'placed %s in the editor level (never saved, removed after PIE)' % BW_TEMP_LABEL)
        except Exception as e:
            note('WARN', 'TEMP capture actor: %r (no scene captures)' % e)
            self.cfg['shots']['enabled'] = False
        os.makedirs(self.shot_dir, exist_ok=True)
        os.makedirs(self.xgrab_dir, exist_ok=True)
        return True

    def arm(self):
        self.phase = 'arming'
        try:
            with open(self.log_path, 'a') as f:
                f.write('\n==== %s %s armed %s\n' % (BW_SCRIPT_VERSION, self.cfg['run_name'], self.R['armed_utc']))
        except Exception:
            pass
        if not self.preflight(arm=True):
            self.check('setup', 'FAIL', 'preflight failed, PIE not started (see preflight lines)')
            self.restore_all()
            self.R['done'] = True
            self.R['reason'] = 'preflight failed'
            self.write(force=True)
            return False
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
        self.phase = 'wait_pie'
        self.R['phase'] = self.phase
        # the run's own bound method: a callback left from an older run can only ever tick that (ended) run
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(force=True)
        print('INFO: armed %s; PIE requested; results -> %s (bw_pie_report.py reads it)' % (self.cfg['run_name'], self.result_path))
        return True

    # ------------------------------------------------------------------ restore / finish

    def restore_all(self):
        rs = self.R['restore']
        try:
            unreal.SystemLibrary.execute_console_command(None, 'Aura.Burrower.DebugRotorBox %d' % int(self.orig.get('cvar_debug_rotor_box', 0) or 0))
            rs['cvar'] = unreal.SystemLibrary.get_console_variable_int_value('Aura.Burrower.DebugRotorBox')
        except Exception as e:
            rs['cvar'] = 'ERROR %r' % e
        try:
            if self.orig.get('settings'):
                rs['settings'] = bw_restore_settings(bw_settings_cdo(), self.orig['settings'])
                rs['settings_after'] = bw_read_settings(bw_settings_cdo())
        except Exception as e:
            rs['settings'] = 'ERROR %r' % e
        try:
            eng = self.orig.get('engine')
            if eng:
                bw_tl_set(bw_engine(), {'bUseFixedFrameRate': bool(eng.get('bUseFixedFrameRate', False)), 'FixedFrameRate': float(eng.get('FixedFrameRate', 30.0))})
                rs['engine'] = bw_tl_get(bw_engine(), ['bUseFixedFrameRate', 'FixedFrameRate'])
        except Exception as e:
            rs['engine'] = 'ERROR %r' % e
        try:
            pl = self.orig.get('play')
            if pl:
                bw_tl_set(bw_play_settings(), {'PlayNetMode': str(pl.get('PlayNetMode')), 'PlayNumberOfClients': int(pl.get('PlayNumberOfClients', 1)),
                                               'RunUnderOneProcess': bool(pl.get('RunUnderOneProcess', True))})
                rs['play'] = bw_tl_get(bw_play_settings(), ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
        except Exception as e:
            rs['play'] = 'ERROR %r' % e
        try:
            os.replace(self.restore_path, self.restore_path + '.restored')
        except Exception:
            pass

    def finish(self, reason, stop=True):
        if self.done:
            return
        self.done = True
        self.R['reason'] = reason
        self.line('INFO', 'finishing: %s' % reason)
        try:
            self.scan_log(final=True)
        except Exception:
            self.err('scan_log')
        for k in BW_CHECK_ORDER:
            if k not in self.R['checks']:
                self.R['checks'][k] = {'status': 'SKIP', 'summary': 'not reached (%s)' % reason, 'data': {}, 't': round(self.now, 2)}
                self.line('WARN', '%s skipped: not reached (%s)' % (k, reason))
        self.restore_all()
        stopped = False
        if stop:
            try:
                same = True
                if self.sw is not None and self.session_real is not None:
                    try:
                        same = unreal.GameplayStatics.get_real_time_seconds(self.sw) >= self.session_real - 0.5
                    except Exception:
                        same = False
                les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
                if les.is_in_play_in_editor():
                    if self.user_play or not same:
                        self.line('WARN', 'not stopping PIE: the log shows "Repeating last play command" or a new session (the user plays)')
                    else:
                        les.editor_request_end_play()
                        stopped = True
            except Exception:
                self.err('endplay')
        self.R['pie_stop_requested'] = stopped
        self.R['done'] = True
        self.R['finished_wall'] = time.time()
        summary = ['%s %s' % (bw_status_word(self.R['checks'][k]['status']), k) for k in BW_CHECK_ORDER]
        self.line('INFO', 'summary: ' + ', '.join(summary))
        self.phase = 'post_end'
        self.post_end_wall = time.time()
        self.write(force=True)
        try:
            shutil.copyfile(self.result_path, os.path.join(self.out_dir, 'pie_result_%s_%s.json' % (self.cfg['run_name'], time.strftime('%Y%m%dT%H%M%S'))))
        except Exception:
            pass

    def post_end(self):
        """After finish: wait for PIE to go, then remove the TEMP_BW_ actor and unregister."""
        try:
            running = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()
        except Exception:
            running = False
        if running and time.time() - self.post_end_wall < self.T['post_end_wall_s']:
            return
        removed = []
        if not running:
            try:
                eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                for a in eas.get_all_level_actors():
                    if a.get_actor_label().startswith('TEMP_BW_'):
                        removed.append(a.get_actor_label())
                        eas.destroy_actor(a)
            except Exception:
                self.err('temp_remove')
            self.line('INFO', 'PIE ended; removed %s from the editor level (the level shows as modified: do not save it)' % removed)
        else:
            self.line('WARN', 'PIE still running %.0f s after the end (user session?): TEMP_BW_ actor left, run bw_pie_cleanup.py later' % self.T['post_end_wall_s'])
        self.R['temp_removed'] = removed
        self.ended = True
        self.write(force=True)
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:
            pass

    # ------------------------------------------------------------------ log

    def scan_log(self, final=False):
        if not self.log_file:
            return
        if not final and time.time() - self.last_log_scan < self.S['log_scan_wall_s']:
            return
        self.last_log_scan = time.time()
        try:
            size = os.path.getsize(self.log_file)
            if size < self.log_offset:
                self.log_offset = 0
            with open(self.log_file, 'rb') as f:
                f.seek(self.log_offset)
                data = f.read(min(size - self.log_offset, 64 * 1024 * 1024))
            # keep a partial last line for next time
            cut = data.rfind(b'\n')
            if cut < 0:
                return
            self.log_offset += cut + 1
            text = data[:cut].decode('utf-8', 'replace')
        except Exception:
            self.err('log_read')
            return
        L = self.R['log_scan']
        pats = {'user_play': 'Repeating last play command', 'burrower_spawn': 'LogBurrowerSpawn', 'burrower': 'LogBurrower:',
                'hit_actor': 'HitActor:', 'bridged': 'Bridged', 'no_playerstart': 'NO PLAYERSTART', 'ensure': 'Ensure condition failed',
                'assert': 'Assertion failed', 'control_rig': 'LogControlRig', 'error': 'Error:', 'python_error': 'LogPython: Error'}
        for ln in text.splitlines():
            for k, p in pats.items():
                if p in ln:
                    e = L.setdefault(k, {'count': 0, 'lines': []})
                    e['count'] += 1
                    if k == 'hit_actor' and 'Burrower' in ln:
                        L.setdefault('hit_burrower', {'count': 0, 'lines': []})
                        L['hit_burrower']['count'] += 1
                        if len(L['hit_burrower']['lines']) < 10:
                            L['hit_burrower']['lines'].append(ln[:300])
                    if len(e['lines']) < 12:
                        e['lines'].append(ln[:300])
                    if k == 'user_play' and not self.user_play:
                        self.user_play = True
                        self.line('WARN', 'the log shows "Repeating last play command": the user pressed Play; this run will not stop PIE')

    # ------------------------------------------------------------------ world state

    def players_in(self, w):
        """{pid: pawn} for the player pawns in world w (PlayerArray, then any non-Burrower character with a PlayerState)."""
        out = {}
        try:
            gs = unreal.GameplayStatics.get_game_state(w)
            for ps in list(bw_get(gs, 'player_array', default=[]) or []):
                try:
                    p = ps.get_pawn()
                    if p is not None and not self.is_burrower(p):
                        out[int(bw_get(ps, 'player_id', 'PlayerId'))] = p
                except Exception:
                    continue
        except Exception:
            pass
        try:
            for c in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.Character):
                if c is None or self.is_burrower(c):
                    continue
                pid = bw_pid_of_pawn(c)
                if pid is not None and pid not in out:
                    out[pid] = c
        except Exception:
            pass
        return out

    def is_burrower(self, a):
        try:
            return isinstance(a, self.bcls) if isinstance(self.bcls, type) else unreal.MathLibrary.class_is_child_of(a.get_class(), self.bcls)
        except Exception:
            return False

    def world_burrowers(self, role, w):
        """Registers new Burrowers of world w, drops gone ones; returns {path: rec} (alive or dead)."""
        recs = self.burrowers[role]
        seen = set()
        try:
            actors = list(unreal.GameplayStatics.get_all_actors_of_class(w, self.bcls))
        except Exception:
            actors = []
        for b in actors:
            try:
                key = b.get_path_name()
            except Exception:
                continue
            seen.add(key)
            if key not in recs:
                recs[key] = self.register_burrower(role, b, key)
            recs[key]['actor'] = b
        for key, rec in recs.items():
            if key not in seen and not rec.get('gone'):
                rec['gone'] = True
                rec['gone_t'] = self.now
                self.event('burrower_gone', role=role, name=rec['name'])
        return recs

    def register_burrower(self, role, b, key):
        rec = {'name': b.get_name(), 'key': key, 'actor': b, 'first_t': self.now, 'role': role, 'missing_bones': [],
               'rest': {}, 'lateral': [], 'rotor': [], 'pipes': {}, 'dist': [], 'health': [], 'dead_t': None}
        try:
            mesh = bw_get(b, 'mesh')
            rec['mesh'] = mesh
            if self.cfg['force_refresh_bones'] and mesh is not None:
                rec['tick_option_before'] = str(bw_get(mesh, 'visibility_based_anim_tick_option'))
                bw_set(mesh, 'visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
        except Exception:
            self.err('register_mesh')
        try:
            rb = bw_get(b, 'rotor_box')
            rec['rotor_box'] = rb
            rec['rotor_extent'] = bw_vec(rb.get_scaled_box_extent()) if rb else (106.0, 156.0, 156.0)
        except Exception:
            rec['rotor_box'] = None
            rec['rotor_extent'] = (106.0, 156.0, 156.0)
        names = list(self.B['body']) + [self.B['rotor']]
        for ch in (self.rig or {}).get('chains', []):
            names += [ch['bones'][0], ch['end_bone']] + self.pipe_mids(ch)
        rec['bones'] = []
        mesh = rec.get('mesh')
        cache = {}
        for n in names:
            try:
                if mesh is not None and mesh.get_bone_index(n) >= 0:
                    rec['bones'].append(n)
                    g = self.ref_global(mesh, n, cache)
                    if g is not None:
                        rec['rest'][n] = (bw_vec(g.translation), bw_quat(g.rotation))
                else:
                    rec['missing_bones'].append(n)
            except Exception:
                rec['missing_bones'].append(n)
        if rec['missing_bones']:
            self.line('WARN', '%s %s: bones missing on the mesh: %s' % (role, rec['name'], rec['missing_bones'][:12]))
        try:
            rec['target_pid'] = self.target_pid(b)
        except Exception:
            rec['target_pid'] = None
        self.event('burrower_seen', role=role, name=rec['name'], target_pid=rec['target_pid'],
                   loc=bw_r(bw_vec(b.get_actor_location())), rest_rotor=bw_r(rec['rest'].get(self.B['rotor'], (None,))[0]) if rec['rest'].get(self.B['rotor']) else None)
        return rec

    def ref_global(self, mesh, name, cache):
        """Component-space reference pose transform of a bone (local ref transforms composed up the parents)."""
        if name in cache:
            return cache[name]
        cache[name] = None
        idx = mesh.get_bone_index(name)
        if idx is None or idx < 0:
            return None
        local = mesh.get_ref_pose_transform(idx)
        parent = str(mesh.get_parent_bone(name))
        g = local
        if parent and parent != 'None':
            pg = self.ref_global(mesh, parent, cache)
            if pg is not None:
                g = local.multiply(pg)
        cache[name] = g
        return g

    @staticmethod
    def pipe_mids(ch):
        bones = ch['bones']
        if len(bones) < 3:
            return list(bones[1:])
        return list(dict.fromkeys([bones[len(bones) // 3], bones[(2 * len(bones)) // 3]]))

    def target_pid(self, b):
        tp = None
        try:
            tp = b.get_target_player()
        except Exception:
            tp = bw_get(b, 'target_player')
        return bw_pid_of_pawn(tp) if tp is not None else None

    def alive_burrowers(self, role):
        out = []
        for rec in self.burrowers[role].values():
            b = rec.get('actor')
            if rec.get('gone') or not bw_valid(b):
                continue
            try:
                if b.is_burrower_dead():
                    continue
            except Exception:
                pass
            out.append(rec)
        return out

    def own_burrower(self, role, pid):
        """The living Burrower that follows player pid in this world, else any living one, else (after KillAll) a dead
        one that still exists, preferring the one that followed pid."""
        al = self.alive_burrowers(role)
        for rec in al:
            try:
                rec['target_pid'] = self.target_pid(rec['actor'])
            except Exception:
                pass
            if rec.get('target_pid') == pid:
                return rec
        if al:
            return al[0]
        dead = [r for r in self.burrowers[role].values() if not r.get('gone') and bw_valid(r.get('actor'))]
        for rec in dead:
            if rec.get('target_pid') == pid:
                return rec
        return dead[0] if dead else None

    def bone_world(self, rec, name):
        try:
            return bw_vec(rec['mesh'].get_bone_transform(name).translation)
        except Exception:
            return None

    def comp_xf(self, rec, name):
        """(t, q) of a bone in component space."""
        mesh = rec['mesh']
        if self.rts_comp is not None:
            x = mesh.get_bone_transform(name, self.rts_comp)
            return bw_vec(x.translation), bw_quat(x.rotation)
        w = mesh.get_bone_transform(name)
        c = mesh.get_world_transform()
        return bw_vec(c.inverse_transform_location(w.translation)), bw_quat(w.rotation)  # UNVERIFIED fallback: rotation stays world

    def health(self, b):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(b)
            if asc is None:
                return None, None
            r = asc.get_gameplay_attribute_value(self.health_attr)
            h = r[0] if isinstance(r, tuple) else r
            r2 = asc.get_gameplay_attribute_value(self.maxhealth_attr)
            m = r2[0] if isinstance(r2, tuple) else r2
            return round(float(h), 2), round(float(m), 2)
        except Exception:
            return None, None

    def health_bar_percent(self, b):
        """Percent of the first UMG ProgressBar inside the Burrower's HealthBar widget (None if unreadable)."""
        try:
            hb = bw_get(b, 'health_bar')
            if hb is None:
                return None
            for pb in unreal.ObjectIterator(unreal.ProgressBar):
                o = pb
                for _ in range(5):
                    o = o.get_outer()
                    if o is None:
                        break
                    if o == hb:
                        return round(float(bw_get(pb, 'percent')), 3)
        except Exception:
            self.err('health_bar')
        return None

    def platforms_in(self, role, w):
        if self.now - self.platform_list_t[role] > 2.0:
            self.platform_list_t[role] = self.now
            d = {}
            try:
                for p in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.MyHexPlatform):
                    try:
                        l = bw_vec(p.get_actor_location())
                        d[(int(round(l[0] / 50.0)), int(round(l[1] / 50.0)), int(round(l[2] / 50.0)))] = p
                    except Exception:
                        continue
            except Exception:
                self.err('platforms')
            self.platform_actors[role] = d
        return self.platform_actors[role]

    # ------------------------------------------------------------------ the tick

    def tick(self, dt):
        if self.ended:
            return
        if self.done:
            self.post_end()
            return
        try:
            if time.time() - self.R['armed_wall'] > self.T['max_wall_s']:
                self.finish('wall-clock timeout %.0f s' % self.T['max_wall_s'])
                return
            try:
                ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
            except Exception:
                ws = []
            if not ws:
                if self.started:
                    self.finish('PIE ended before the test finished (stopped by the user or a crash in the game)', stop=False)
                elif time.time() - self.R['armed_wall'] > self.T['pie_start_timeout_wall_s']:
                    self.finish('PIE did not start within %.0f s (no active level viewport?)' % self.T['pie_start_timeout_wall_s'], stop=False)
                return
            roles = {}
            for w in ws:
                roles.setdefault(bw_role(w), w)
            sw = roles.get('server') or roles.get('standalone') or ws[0]
            cw = roles.get('client')
            self.ws, self.sw, self.cw = ws, sw, cw
            self.now = float(unreal.GameplayStatics.get_time_seconds(sw))
            real = float(unreal.GameplayStatics.get_real_time_seconds(sw))
            if self.session_real is not None and real < self.session_real - 1.0:
                self.finish('a new PIE session started (not ours)', stop=False)
                return
            self.session_real = real
            if not self.started:
                self.started = True
                self.event('pie_started', worlds=[bw_role(w) for w in ws])
                self.line('INFO', 'PIE started: %s' % [bw_role(w) for w in ws])
                self.set_phase('wait_pawns')
            if self.now > self.T['max_game_s']:
                self.finish('game-time limit %.0f s' % self.T['max_game_s'])
                return
            self.fps_update()
            self.scan_log()
            for role, w in (('server', sw), ('client', cw)):
                if w is not None:
                    try:
                        self.world_burrowers(role, w)
                        self.rotor_track(role)
                    except Exception:
                        self.err('burrowers_' + role)
            self.step_phase()
            if self.done:
                return
            for role, w in (('server', sw), ('client', cw)):
                if w is not None:
                    try:
                        self.steer(role, w)
                    except Exception:
                        self.err('steer_' + role)
            self.sample()
            self.shots_step()
            self.write()
        except Exception:
            self.err('tick')
            self.write(force=True)
            if self.err_count > 60:
                self.finish('too many errors (see errors)')

    def fps_update(self):
        wall = time.time()
        if self.wall_last is None or wall - self.wall_last >= 2.0:
            if self.wall_last is not None and wall > self.wall_last:
                rate = float(self.cfg.get('fixed_frame_rate') or 30.0)
                self.fps = round(rate * (self.now - self.game_last) / (wall - self.wall_last), 1)
            self.wall_last, self.game_last = wall, self.now

    def set_phase(self, name):
        self.phase = name
        self.phase_t0 = self.now
        self.R['phase'] = name
        self.event('phase', name=name)
        self.write(force=True)

    def pt(self):
        return self.now - self.phase_t0

    def due(self, key, dt):
        if self.now >= self.next.get(key, -1e9):
            self.next[key] = self.now + dt
            return True
        return False

    def console(self, cmd, w=None):
        w = w or self.sw
        unreal.SystemLibrary.execute_console_command(w, cmd)
        self.event('console', cmd=cmd, world=bw_role(w))
        self.line('INFO', 'console (%s world): %s' % (bw_role(w), cmd))

    # ------------------------------------------------------------------ phases

    def step_phase(self):
        ph = self.phase
        if ph == 'wait_pawns':
            self.ph_wait_pawns()
        elif ph == 'warmup':
            self.ph_warmup()
        elif ph == 'spawn':
            self.ph_spawn()
        elif ph == 'follow':
            if self.pt() >= self.T['follow_s']:
                self.eval_follow()
                self.choose_hover_points()
                self.set_phase('cut')
        elif ph == 'cut':
            if self.pt() >= self.T['cut_s']:
                self.set_phase('cut_settle')
        elif ph == 'cut_settle':
            if self.pt() >= self.T['replication_wait_s'] + 1.0:
                self.eval_tiles()
                self.set_phase('damage')
                self.damage_begin()
        elif ph == 'damage':
            self.ph_damage()
        elif ph == 'kill':
            self.ph_kill()
        elif ph == 'respawn':
            self.ph_respawn()
        elif ph == 'respawned':
            if self.pt() >= self.T['respawned_extra_s']:
                self.finish('ok')

    def ph_wait_pawns(self):
        want_worlds = 2 if self.cfg['play']['net_mode'] == 'PIE_ListenServer' and int(self.cfg['play']['num_clients']) >= 2 else 1
        want_players = max(int(self.cfg['play']['num_clients']), 1)
        sp = self.players_in(self.sw)
        # per player: when its pawn first appeared (the spawner's FirstSpawnDelay counts from there)
        for pid, pawn in sp.items():
            if pid not in self.players:
                self.players[pid] = {'first_pawn_t': self.now, 'name': pawn.get_name()}
                self.event('pawn_seen', pid=pid, pawn=pawn.get_name())
        # a player controller left without a pawn (StartupMap's PlayerStart rejected) is restarted next to the host
        if self.pt() > self.T['restart_missing_pawn_after_s']:
            try:
                host = bw_local_pc(self.sw)
                host_pawn = host.get_controlled_pawn() if host else None
                if host_pawn:
                    for pc in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.PlayerController):
                        key = pc.get_name()
                        if pc.get_controlled_pawn() is None and key not in self.missing_restarted:
                            self.missing_restarted.add(key)
                            loc = bw_add(bw_vec(host_pawn.get_actor_location()), (0.0, 400.0, 300.0))
                            gm = unreal.GameplayStatics.get_game_mode(self.sw)
                            gm.restart_player_at_transform(pc, unreal.Transform(location=bw_uvec(loc), rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0)))
                            p = pc.get_controlled_pawn()
                            self.event('restart_player_at_transform', pc=key, loc=bw_r(loc), pawn=p.get_name() if p else None)
                            self.line('WARN', 'player controller %s had no pawn (StartupMap PlayerStart issue): restarted next to the host -> %s' % (key, p.get_name() if p else None))
            except Exception:
                self.err('restart_player')
        if len(self.ws) >= want_worlds and len(sp) >= want_players:
            dd = {}
            for pid, pawn in sp.items():
                dd[pid] = bw_get(pawn, 'debug_die_after_begin_play_seconds')
            self.R['players'] = {str(k): {'pawn': v.get_name(), 'loc': bw_r(bw_vec(v.get_actor_location())), 'debug_die_s': dd.get(k)} for k, v in sp.items()}
            data = {'worlds': [bw_role(w) for w in self.ws], 'players': self.R['players'], 'restarted': sorted(self.missing_restarted),
                    'play_settings': self.R.get('play_settings_during') or self.R.get('play_settings_before')}
            bad_dd = [k for k, v in dd.items() if v]
            try:
                gm = unreal.GameplayStatics.get_game_mode(self.sw)
                data['game_mode'] = gm.get_class().get_path_name() if gm else None
                data['class_info'] = bw_class_path(bw_get(gm, 'da_my_enemy_character_class_info', 'DA_MyEnemyCharacterClassInfo')) if gm else None
            except Exception:
                data['class_info'] = '?'
            no_ci = data.get('class_info') in (None, 'None')
            self.check('setup', 'WARN' if (bad_dd or self.missing_restarted or no_ci) else 'PASS',
                       'worlds %s, %d players with pawns%s%s%s' % (data['worlds'], len(sp),
                                                                  ', restarted %s' % sorted(self.missing_restarted) if self.missing_restarted else '',
                                                                  ', DebugDieAfterBeginPlaySeconds>0 on %s' % bad_dd if bad_dd else '',
                                                                  ', GameMode %s has no DA_MyEnemyCharacterClassInfo (spawns refused)' % data.get('game_mode') if no_ci else ''), data)
            self.spawn = {'t0': None, 'by_pid': {}, 'fallback_done': False, 'cmd_t': None}
            self.set_phase('warmup')
            return
        if self.pt() > self.T['pawn_timeout_s']:
            self.check('setup', 'FAIL', 'after %.0f s: %d worlds (want %d), %d player pawns (want %d). Listen server + client not running? Check the ini (bw_ini_playmode.sh) / PlayNumberOfClients=2' % (
                self.T['pawn_timeout_s'], len(self.ws), want_worlds, len(sp), want_players), {'worlds': [bw_role(w) for w in self.ws], 'pawns': list(sp.keys())})
            self.finish('setup failed')

    def ph_warmup(self):
        if self.cfg['spawn_mode'] != 'spawnnow':
            self.auto_record()
        if self.pt() < self.T['warmup_s']:
            return
        if not self.platforms_in('server', self.sw) and self.pt() < self.T['warmup_s'] + 20.0:
            if self.due('warmup_note', 5.0):
                self.line('INFO', 'no AMyHexPlatform in the server world yet, waiting')
            return
        try:
            self.paths = list(unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.MyHexPathSpawner))
        except Exception:
            self.paths = []
        if self.cfg['debug_rotor_box']:
            try:
                self.console('Aura.Burrower.DebugRotorBox 1')
                self.R['cvar_debug_rotor_box'] = unreal.SystemLibrary.get_console_variable_int_value('Aura.Burrower.DebugRotorBox')
            except Exception:
                self.err('cvar')
        self.spawn['t0'] = self.now
        self.set_phase('spawn')
        if self.cfg['spawn_mode'] == 'spawnnow':
            self.spawn_now_all()

    def spawn_now_all(self, only_pids=None):
        try:
            gs = unreal.GameplayStatics.get_game_state(self.sw)
            arr = list(bw_get(gs, 'player_array', default=[]) or [])
        except Exception:
            arr = []
        idxs = range(len(arr)) if self.cfg['spawn_indices'] == 'all' else list(self.cfg['spawn_indices'])
        before = set(self.burrowers['server'].keys())
        self.spawn['cmd_t'] = self.now
        for i in idxs:
            try:
                pid = int(bw_get(arr[i], 'player_id', 'PlayerId')) if i < len(arr) else None
            except Exception:
                pid = None
            if only_pids is not None and pid not in only_pids:
                continue
            pawn = None
            try:
                pawn = arr[i].get_pawn()
            except Exception:
                pass
            pre = self.pawn_state(pawn)
            self.console('Aura.Burrower.SpawnNow %d' % i)
            recs = self.world_burrowers('server', self.sw)
            for key, rec in recs.items():
                if key in before:
                    continue
                before.add(key)
                self.spawn_record(rec, pre)

    def pawn_state(self, pawn):
        if pawn is None:
            return None
        try:
            loc = bw_vec(pawn.get_actor_location())
            vel = bw_vec(pawn.get_velocity())
            fwd = bw_vec(pawn.get_actor_forward_vector())
            return {'pid': bw_pid_of_pawn(pawn), 'loc': loc, 'vel': vel, 'fwd': fwd}
        except Exception:
            return None

    def spawn_record(self, rec, pre):
        """Geometry of a new Burrower against its player at spawn (server)."""
        b = rec['actor']
        try:
            pid = self.target_pid(b)
            rec['target_pid'] = pid
            if pre is None or pre.get('pid') != pid:
                pawn = self.players_in(self.sw).get(pid)
                pre = self.pawn_state(pawn)
            if pre is None:
                return
            sett = self.R.get('settings_during') or {}
            sdb = float(sett.get('SpawnDistanceBehind', 3000.0))
            sho = float(sett.get('SpawnHeightOffset', -150.0))
            minv = float(sett.get('MinSpeedForVelocityDirection', 150.0))
            loc = bw_vec(b.get_actor_location())
            rel = bw_sub(loc, pre['loc'])
            v2 = (pre['vel'][0], pre['vel'][1], 0.0)
            if bw_len2d(v2) > max(minv, 1.0):
                behind = bw_mul(bw_norm(v2), -1.0)
                frm = 'velocity'
            else:
                f2 = bw_norm((pre['fwd'][0], pre['fwd'][1], 0.0))
                behind = bw_mul(f2, -1.0) if bw_len(f2) > 0 else (-1.0, 0.0, 0.0)
                frm = 'facing'
            rel2 = (rel[0], rel[1], 0.0)
            dot = bw_dot(bw_norm(rel2), behind) if bw_len2d(rel2) > 1 else 0.0
            d = {'burrower': rec['name'], 'pid': pid, 't': round(self.now, 2), 'dist_h': round(bw_len2d(rel), 1), 'dz': round(rel[2], 1),
                 'behind_dot': round(dot, 3), 'behind_from': frm, 'expected_dist': sdb, 'expected_dz': sho,
                 'pawn_speed2d': round(bw_len2d(v2), 1), 'loc': bw_r(loc), 'pawn_loc': bw_r(pre['loc'])}
            d['ok'] = (abs(d['dist_h'] - sdb) <= self.TH['spawn_dist_tol_frac'] * sdb + 50.0 and abs(d['dz'] - sho) <= self.TH['spawn_z_tol_cm']
                       and dot >= self.TH['spawn_behind_dot_min'])
            if pid in self.players:
                d['since_first_pawn_s'] = round(self.now - self.players[pid]['first_pawn_t'], 2)
            self.spawn['by_pid'].setdefault(pid, []).append(d)
            self.event('spawned', **d)
        except Exception:
            self.err('spawn_record')

    def auto_record(self):
        """Auto mode: the spawn geometry of every Burrower the spawner made, the frame it is first seen."""
        known = set()
        for v in self.spawn['by_pid'].values():
            known |= set(x['burrower'] for x in v)
        for rec in self.alive_burrowers('server'):
            if rec['name'] not in known:
                self.spawn_record(rec, None)

    def ph_spawn(self):
        pids = list(self.players.keys())
        # auto mode: record spawns as they appear
        if self.cfg['spawn_mode'] != 'spawnnow':
            self.auto_record()
            missing = [p for p in pids if p not in self.spawn['by_pid']]
            if missing and self.pt() > self.T['auto_spawn_timeout_s'] and not self.spawn['fallback_done']:
                self.spawn['fallback_done'] = True
                self.line('WARN', 'no automatic spawn for players %s after %.0f s: running Aura.Burrower.SpawnNow for them' % (missing, self.pt()))
                self.spawn_now_all(only_pids=set(missing))
            if missing and not self.spawn['fallback_done']:
                return
            if self.spawn.get('all_t') is None:
                self.spawn['all_t'] = self.now
        else:
            if self.spawn.get('all_t') is None:
                self.spawn['all_t'] = self.now
        if self.now - self.spawn['all_t'] < self.T['replication_wait_s']:
            return
        self.eval_spawn()
        if not self.alive_burrowers('server'):
            self.finish('no Burrower spawned')
            return
        self.set_phase('follow')

    # ------------------------------------------------------------------ checks a, b, c, d, f

    def eval_spawn(self):
        pids = list(self.players.keys())
        sv = {}
        for rec in self.alive_burrowers('server'):
            pid = self.target_pid(rec['actor'])
            sv.setdefault(pid, []).append(rec)
        cl = {}
        for rec in self.alive_burrowers('client'):
            pid = self.target_pid(rec['actor'])
            cl.setdefault(pid, []).append(rec)
        data = {'mode': self.cfg['spawn_mode'], 'spawns': self.spawn['by_pid'], 'server': {}, 'client': {}}
        ok = True
        notes = []
        sett = self.R.get('settings_during') or {}
        for pid in pids:
            s = sv.get(pid, [])
            c = cl.get(pid, [])
            data['server'][pid] = [r['name'] for r in s]
            data['client'][pid] = [r['name'] for r in c]
            sp = self.spawn['by_pid'].get(pid, [])
            geo_ok = bool(sp) and all(x['ok'] for x in sp)
            pos_err = None
            if s and c:
                try:
                    pos_err = round(bw_len(bw_sub(bw_vec(s[0]['actor'].get_actor_location()), bw_vec(c[0]['actor'].get_actor_location()))), 1)
                except Exception:
                    pass
            data.setdefault('client_pos_err', {})[pid] = pos_err
            good = len(s) == 1 and len(c) == 1 and geo_ok and (pos_err is None or pos_err <= self.TH['client_pos_tol_cm'])
            if self.cfg['spawn_mode'] != 'spawnnow' and sp and 'since_first_pawn_s' in sp[0]:
                fsd = float(sett.get('FirstSpawnDelay', 0))
                late = sp[0]['since_first_pawn_s']
                data.setdefault('auto_delay', {})[pid] = {'since_first_pawn_s': late, 'FirstSpawnDelay': fsd}
                if not (fsd - 0.5 <= late <= fsd + 1.5):
                    notes.append('player %s auto spawn after %.1f s (FirstSpawnDelay %.1f)' % (pid, late, fsd))
                    good = False
            if not good:
                ok = False
                notes.append('player %s: server %d, client %d, geometry %s, client pos err %s' % (
                    pid, len(s), len(c), [(x['dist_h'], x['dz'], x['behind_dot']) for x in sp], pos_err))
        if self.cfg['spawn_mode'] != 'spawnnow' and self.spawn.get('fallback_done'):
            ok = False
            notes.append('automatic spawn missing, SpawnNow fallback used')
        geo = ['p%s %s cm behind (dz %s, dot %s, by %s)' % (pid, x['dist_h'], x['dz'], x['behind_dot'], x['behind_from'])
               for pid, v in self.spawn['by_pid'].items() for x in v[:1]]
        self.check('a_spawn', 'PASS' if ok else 'FAIL', ('one Burrower per player on server and client; ' + '; '.join(geo)) if ok else '; '.join(notes), data)

    def eval_follow(self):
        # b: distance to the target over the follow window (server), and on the client for information
        res = {'server': {}, 'client': {}}
        ok = True
        notes = []
        for role in ('server', 'client'):
            for rec in self.burrowers[role].values():
                ds = rec['dist']
                if len(ds) < 4:
                    continue
                d0 = ds[0][1]
                tail = [d for t, d, tr in ds if t >= ds[-1][0] - 2.0]
                d_end = sum(tail) / len(tail)
                d_max = max(d for t, d, tr in ds)
                travel = ds[-1][2]
                r = {'pid': rec.get('target_pid'), 'd0': round(d0, 1), 'd_end': round(d_end, 1), 'd_max': round(d_max, 1), 'travel': round(travel, 1),
                     'n': len(ds), 'series': [[round(t, 1), round(d, 0)] for t, d, tr in ds[::2]]}
                if role == 'server':
                    r['ok'] = ((d_end < d0 - 200.0 or d_end <= self.TH['follow_end_max_cm']) and d_max <= d0 + self.TH['follow_bound_extra_cm']
                               and travel >= self.TH['follow_min_travel_cm'])
                    if not r['ok']:
                        ok = False
                        notes.append('%s: d0 %.0f -> end %.0f (max %.0f), travelled %.0f cm' % (rec['name'], d0, d_end, d_max, travel))
                res[role][rec['name']] = r
        if not res['server']:
            self.check('b_follow', 'FAIL', 'no distance samples', res)
        else:
            s = ['%s: %.0f -> %.0f cm (max %.0f, travel %.0f)' % (k, v['d0'], v['d_end'], v['d_max'], v['travel']) for k, v in res['server'].items()]
            self.check('b_follow', 'PASS' if ok else 'FAIL', '; '.join(s if ok else notes), res)
        self.eval_wave()
        self.eval_rotor()
        self.eval_pipes()

    def eval_wave(self):
        res = {}
        ok = True
        any_data = False
        notes = []
        for role in ('server', 'client'):
            for rec in self.burrowers[role].values():
                lat = rec['lateral']
                if len(lat) < 10:
                    continue
                any_data = True
                st4 = bw_osc_stats([x[3] for x in lat])
                st2 = bw_osc_stats([x[1] for x in lat])
                both = [x for x in lat if x[1] is not None and x[3] is not None]
                lag = bw_lag([x[1] for x in both], [x[3] for x in both], int(1.0 / max(self.S['pose_dt'], 0.01)))
                amp = [x[4] for x in lat if x[4] is not None]
                wt = [x[5] for x in lat if x[5] is not None]
                r = {'j4_rel_j0_y': st4, 'j2_rel_j0_y': st2, 'lag_j2_to_j4_samples': lag,
                     'anim_wave_amp_deg': [bw_r(min(amp), 2), bw_r(max(amp), 2)] if amp else None,
                     'anim_wave_time_range': [bw_r(min(wt), 3), bw_r(max(wt), 3)] if wt else None,
                     'series_j4': [[round(x[0], 2), round(x[3], 1)] for x in lat[::2]]}
                good = bool(st4) and st4['p2p'] >= self.TH['wave_min_p2p_cm'] and st4['crossings'] >= self.TH['wave_min_crossings']
                r['ok'] = good
                if not good:
                    ok = False
                    notes.append('%s %s: J4 sideways p2p %s cm, %s crossings, anim amplitude %s' % (role, rec['name'], st4 and st4['p2p'], st4 and st4['crossings'], r['anim_wave_amp_deg']))
                res['%s:%s' % (role, rec['name'])] = r
        if not any_data:
            self.check('c_wave', 'FAIL', 'no pose samples (mesh/bones missing?)', res)
            return
        s = ['%s p2p %.0f cm, %d crossings, lag %s' % (k, v['j4_rel_j0_y']['p2p'], v['j4_rel_j0_y']['crossings'], v['lag_j2_to_j4_samples']) for k, v in res.items() if v.get('j4_rel_j0_y')]
        self.check('c_wave', 'PASS' if ok else 'FAIL', '; '.join(s) if ok else '; '.join(notes) + ' (wave pins on the Control Rig node wired?)', res)

    def eval_rotor(self):
        res = {}
        ok = True
        notes = []
        any_data = False
        rest_cfg = tuple(self.B['rotor_rest_cm'])
        for role in ('server', 'client'):
            for rec in self.burrowers[role].values():
                smp = rec['rotor']
                if len(smp) < 5:
                    continue
                any_data = True
                rest = rec['rest'].get(self.B['rotor'])
                rest_loc = rest[0] if rest else rest_cfg
                q0 = smp[0][2]
                total = 0.0
                prev = None
                max_step = 0.0
                swing_max = 0.0
                drift_max = 0.0
                for t, loc, q, anim in smp:
                    tw, sg = bw_twist_swing_x(bw_qmul(q, bw_qconj(q0)))
                    if prev is not None:
                        step = bw_wrap180(tw - prev)
                        total += step
                        max_step = max(max_step, abs(step))
                    prev = tw
                    swing_max = max(swing_max, sg)
                    drift_max = max(drift_max, bw_len(bw_sub(loc, rest_loc)))
                dur = smp[-1][0] - smp[0][0]
                anim_a = [x[3] for x in smp if x[3] is not None]
                anim_turn = None
                if len(anim_a) >= 2:
                    anim_turn = 0.0
                    for i in range(1, len(anim_a)):
                        anim_turn += bw_wrap180(anim_a[i] - anim_a[i - 1])
                r = {'samples': len(smp), 'duration_s': round(dur, 2), 'bone_turn_deg': round(total, 1), 'bone_rate_deg_s': round(total / dur, 1) if dur > 0 else None,
                     'anim_turn_deg': bw_r(anim_turn), 'max_step_deg': round(max_step, 1), 'axis_swing_max_deg': round(swing_max, 2),
                     'loc_drift_max_cm': round(drift_max, 2), 'rest_loc': bw_r(rest_loc), 'rest_cfg': list(rest_cfg),
                     'rest_vs_cfg_cm': round(bw_len(bw_sub(rest_loc, rest_cfg)), 1)}
                good = abs(total) >= self.TH['rotor_min_turn_deg'] and drift_max <= self.TH['rotor_loc_tol_cm'] and swing_max <= self.TH['rotor_axis_tol_deg']
                if max_step > self.TH['rotor_alias_deg_per_sample']:
                    r['warning'] = 'steps up to %.0f deg per sample: the unwrapped angle may alias (frame rate too low?)' % max_step
                r['ok'] = good
                if not good:
                    ok = False
                    notes.append('%s %s: bone turned %.0f deg (anim %s), drift %.1f cm, axis swing %.1f deg' % (role, rec['name'], total, bw_r(anim_turn), drift_max, swing_max))
                res['%s:%s' % (role, rec['name'])] = r
        if not any_data:
            self.check('d_rotor', 'FAIL', 'no rotor samples', res)
            return
        s = ['%s %.0f deg in %.1f s (%.0f deg/s), drift %.2f cm, swing %.2f deg' % (k, v['bone_turn_deg'], v['duration_s'], v['bone_rate_deg_s'] or 0, v['loc_drift_max_cm'], v['axis_swing_max_deg']) for k, v in res.items()]
        self.check('d_rotor', 'PASS' if ok else 'FAIL', '; '.join(s) if ok else '; '.join(notes), res)

    def eval_pipes(self):
        chains = (self.rig or {}).get('chains', [])
        if not chains:
            self.check('f_pipes', 'SKIP', 'no rig info chains')
            return
        res = {}
        status = 'PASS'
        notes = []
        any_data = False
        for role in ('server', 'client'):
            for rec in self.burrowers[role].values():
                if not rec['pipes']:
                    continue
                any_data = True
                per = {}
                still = []
                for ch in chains:
                    p = rec['pipes'].get(ch['name'])
                    if not p:
                        continue
                    mids = {k: round(v.std(), 2) for k, v in p['mid'].items()}
                    per[ch['name']] = {'type': ch.get('type'), 'rest_d01': bw_r(p['rest01']), 'rest_dend': bw_r(p['restend']),
                                       'drift01_max': round(p['drift01'], 2), 'driftend_max': round(p['driftend'], 2),
                                       'local01_max': round(p['loc01'], 2), 'localend_max': round(p['locend'], 2), 'mid_std_cm': mids,
                                       'n': p['n']}
                    if p['drift01'] > self.TH['pipe_anchor_tol_cm'] or p['driftend'] > self.TH['pipe_anchor_tol_cm']:
                        status = 'FAIL'
                        notes.append('%s %s %s: anchor drift _01 %.1f / _end %.1f cm' % (role, rec['name'], ch['name'], p['drift01'], p['driftend']))
                    if not mids or max(mids.values()) < self.TH['pipe_mid_min_std_cm']:
                        still.append(ch['name'])
                if still and len(still) == len(per):
                    status = 'FAIL'
                    notes.append('%s %s: no middle bone moved relative to J1 (dynamics not running?)' % (role, rec['name']))
                elif still and status == 'PASS':
                    status = 'WARN'
                    notes.append('%s %s: still chains %s' % (role, rec['name'], still))
                res['%s:%s' % (role, rec['name'])] = per
        if not any_data:
            self.check('f_pipes', 'FAIL', 'no pipe samples (pipe bones missing?)', res)
            return
        drifts = [max(c['drift01_max'], c['driftend_max']) for per in res.values() for c in per.values()]
        worst = max(drifts) if drifts else -1.0
        self.check('f_pipes', status, ('anchors within %.2f cm of rest, middle bones move (J1-local std up to %.1f cm)' % (
            worst, max([m for per in res.values() for c in per.values() for m in c['mid_std_cm'].values()] or [0.0]))) if status == 'PASS' else '; '.join(notes), res)

    # ------------------------------------------------------------------ check e (tiles)

    def rotor_track(self, role):
        h = self.rotor_hist[role]
        for rec in self.alive_burrowers(role):
            rb = rec.get('rotor_box')
            if rb is None:
                continue
            try:
                h.append((self.now, bw_vec(rb.get_world_location()), rec['rotor_extent']))
            except Exception:
                continue
        while h and h[0][0] < self.now - 3.0:
            h.pop(0)

    def tiles_step(self, role, w):
        plats = self.platforms_in(role, w)
        rot = self.rotor_hist[role]
        if not rot and not self.platforms[role]:
            return
        rad = self.S['tile_track_radius']
        recs = self.platforms[role]
        for key, p in plats.items():
            if key in recs:
                continue
            try:
                o, e = p.get_actor_bounds(False)
                o = bw_vec(o)
                e = bw_vec(e)
                near = any(bw_len2d(bw_sub(c, o)) - math.hypot(e[0], e[1]) < rad for t, c, ex in rot[-6:])
                if not near:
                    continue
                ism = bw_get(p, 'hex_pillars_ism')
                tiles = bw_ism_tiles(ism)
                if tiles is None:
                    continue
                hr = float(bw_get(p, 'hex_radius', default=100.0) or 100.0)
                sc = bw_vec(p.get_actor_scale3d())
                recs[key] = {'actor': p, 'ism': ism, 'tiles': tiles, 'count': len(tiles), 'start_count': len(tiles), 'name': p.get_name(),
                             'bottom': bool(bw_get(p, 'is_bottom_platform', default=False)), 'hex_r': hr * max(abs(sc[0]), abs(sc[1])),
                             'removed': [], 'last_t': self.now}
                self.event('platform_tracked', role=role, name=p.get_name(), tiles=len(tiles))
            except Exception:
                self.err('track_platform')
        for key, r in list(recs.items()):
            try:
                if not bw_valid(r['actor']):
                    r['gone'] = True
                    continue
                n = r['ism'].get_instance_count()
                if n == r['count']:
                    r['last_t'] = self.now
                    continue
                tiles = bw_ism_tiles(r['ism'])
                if tiles is None:
                    continue
                gone = [k for k in r['tiles'] if k not in tiles]
                for k in gone:
                    pos = r['tiles'][k]
                    best = None
                    for t, c, ex in rot:
                        if t < r['last_t'] - 0.2:
                            continue
                        d = bw_len2d(bw_sub(pos, c))
                        if best is None or d < best[0]:
                            best = (d, c, ex)
                    cls = 'other'
                    thr = None
                    if best is not None:
                        ex = best[2]
                        thr = math.hypot(ex[0], ex[1]) + 1.2 * r['hex_r'] + self.TH['tile_cut_extra_cm']
                        if best[0] <= thr and best[1][2] - ex[2] <= pos[2] + 50.0:
                            cls = 'rotor'
                    r['removed'].append({'t': round(self.now, 2), 'key': list(k), 'pos': bw_r(pos), 'cls': cls,
                                         'rotor_d': bw_r(best[0]) if best else None, 'thr': bw_r(thr), 'rotor_z': bw_r(best[1][2]) if best else None})
                r['tiles'] = tiles
                r['count'] = len(tiles)
                r['last_t'] = self.now
            except Exception:
                self.err('tiles_' + role)

    def eval_tiles(self):
        # fresh client snapshot of every platform the server tracked
        cplats = self.platforms_in('client', self.cw) if self.cw is not None else {}
        res = {'platforms': {}, 'server_rotor_cuts': 0, 'server_other': 0, 'client_rotor_cuts': 0, 'still_standing_on_client': [],
               'count_mismatch': []}
        for key, r in self.platforms['server'].items():
            if r.get('gone'):
                continue
            try:
                stiles = bw_ism_tiles(r['ism']) or r['tiles']
            except Exception:
                stiles = r['tiles']
            ctiles = None
            ca = cplats.get(key)
            if ca is None:
                try:
                    ca = bw_match_actor(cplats, bw_vec(r['actor'].get_actor_location()), 200.0)
                except Exception:
                    ca = None
            if ca is not None:
                try:
                    ctiles = bw_ism_tiles(bw_get(ca, 'hex_pillars_ism'))
                except Exception:
                    ctiles = None
            rotor = [x for x in r['removed'] if x['cls'] == 'rotor']
            other = [x for x in r['removed'] if x['cls'] != 'rotor']
            standing = [x['key'] for x in rotor if ctiles is not None and bw_near_tile(ctiles, x['pos'], 30.0)]
            crec = self.platforms['client'].get(key)
            pr = {'name': r['name'], 'bottom': r['bottom'], 'start': r['start_count'], 'server_now': len(stiles),
                  'client_now': len(ctiles) if ctiles is not None else None, 'rotor_cuts': len(rotor), 'other': len(other),
                  'rotor_detail': rotor[:12], 'client_rotor_cuts': len([x for x in crec['removed'] if x['cls'] == 'rotor']) if crec else None}
            res['platforms'][r['name']] = pr
            res['server_rotor_cuts'] += len(rotor)
            res['server_other'] += len(other)
            res['client_rotor_cuts'] += pr['client_rotor_cuts'] or 0
            res['still_standing_on_client'] += [[r['name']] + list(k) for k in standing]
            if ctiles is not None and len(ctiles) != len(stiles):
                res['count_mismatch'].append([r['name'], len(stiles), len(ctiles)])
            if ctiles is None and rotor:
                res['count_mismatch'].append([r['name'], len(stiles), 'client platform not found'])
        res['cut_diag'] = self.R['series'].get('cut_diag', [])[-12:]
        n = res['server_rotor_cuts']
        if n < self.TH['tiles_min_cut']:
            st = 'FAIL'
            msg = 'no tile collapsed near a rotor box on the server (%d other collapses); see cut_diag (rotor vs tile height)' % res['server_other']
        elif res['still_standing_on_client']:
            st = 'FAIL'
            msg = '%d rotor cuts on the server, but %d of them still stand on the client' % (n, len(res['still_standing_on_client']))
        elif res['count_mismatch']:
            st = 'WARN'
            msg = '%d rotor cuts, all gone on the client too; tile counts differ on %s (other collapses in flight?)' % (n, res['count_mismatch'])
        else:
            st = 'PASS'
            msg = '%d tiles collapsed at the rotor on the server (%d on the client by its own rotor track), counts match on %d tracked platforms' % (
                n, res['client_rotor_cuts'], len(res['platforms']))
        self.check('e_tiles', st, msg, res)

    # ------------------------------------------------------------------ steering

    def lane_target(self, pid, loc):
        pl = self.players.setdefault(pid, {'first_pawn_t': self.now}) if pid is not None else {}
        if not self.paths:
            return None
        names = [p.get_path_name() for p in self.paths if bw_valid(p)]
        lane = pl.get('lane')
        if lane is None or lane not in names:
            best = None
            for p in self.paths:
                try:
                    sp = p.get_path_spline()
                    k = sp.find_input_key_closest_to_world_location(bw_uvec(loc))
                    d = bw_len(bw_sub(bw_vec(sp.get_location_at_spline_input_key(k, unreal.SplineCoordinateSpace.WORLD)), loc))
                    if best is None or d < best[0]:
                        best = (d, p.get_path_name())
                except Exception:
                    continue
            if best is None:
                return None
            lane = best[1]
            pl['lane'] = lane
        path = [p for p in self.paths if p.get_path_name() == lane][0]
        sp = path.get_path_spline()
        k = sp.find_input_key_closest_to_world_location(bw_uvec(loc))
        d = sp.get_distance_along_spline_at_spline_input_key(k)
        tgt = bw_vec(sp.get_location_at_distance_along_spline(min(d + self.M['ahead'], sp.get_spline_length()), unreal.SplineCoordinateSpace.WORLD))
        return bw_add(tgt, (0.0, 0.0, self.M['follow_z']))

    def choose_hover_points(self):
        """Cut phase: each player hovers cut_hover_z above a standing tile near the point cut_ahead along its lane."""
        sp = self.players_in(self.sw)
        plats = self.platforms_in('server', self.sw)
        for pid, pawn in sp.items():
            try:
                loc = bw_vec(pawn.get_actor_location())
                ahead = self.lane_target(pid, loc)
                aim = loc
                if ahead is not None:
                    dirv = bw_norm((ahead[0] - loc[0], ahead[1] - loc[1], 0.0))
                    aim = bw_add(loc, bw_mul(dirv, self.M['cut_ahead']))
                cands = []
                for key, p in plats.items():
                    try:
                        o, e = p.get_actor_bounds(False)
                        if bw_len2d(bw_sub(bw_vec(o), aim)) - math.hypot(e.x, e.y) > 3000.0:
                            continue
                        r = self.platforms['server'].get(key)
                        tiles = r['tiles'] if r else bw_ism_tiles(bw_get(p, 'hex_pillars_ism'))
                        for k, pos in (tiles or {}).items():
                            cands.append((bw_len2d(bw_sub(pos, aim)), pos, p.get_name()))
                    except Exception:
                        continue
                cands.sort(key=lambda c: c[0])
                chosen = None
                for d, pos, pname in cands[:25]:
                    pt = bw_add(pos, (0.0, 0.0, self.M['cut_hover_z']))
                    try:
                        hits = unreal.SystemLibrary.sphere_overlap_components(self.sw, bw_uvec(pt), self.M['clear_radius'], bw_obj_types(), None, [pawn])
                    except Exception:
                        hits = None
                    if not hits:
                        chosen = (pt, pos, pname, d)
                        break
                if chosen is None and cands:
                    d, pos, pname = cands[0]
                    chosen = (bw_add(pos, (0.0, 0.0, self.M['cut_hover_z'])), pos, pname, d)
                pl = self.players.setdefault(pid, {'first_pawn_t': self.now})
                if chosen:
                    pl['hover'] = chosen[0]
                    self.event('hover_point', pid=pid, point=bw_r(chosen[0]), tile_top=bw_r(chosen[1]), platform=chosen[2], dist_from_aim=bw_r(chosen[3]))
                else:
                    pl['hover'] = loc
                    self.line('WARN', 'player %s: no tile near its path to hover over; it holds where it is' % pid)
            except Exception:
                self.err('hover_point')

    def ensure_flying(self, pawn):
        try:
            cmc = pawn.get_component_by_class(unreal.CharacterMovementComponent)
            if not cmc:
                return
            key = pawn.get_path_name()
            if key not in self.flying or bw_get(cmc, 'movement_mode') != unreal.MovementMode.MOVE_FLYING:
                bw_set(cmc, 'max_fly_speed', float(self.M['speed']))
                bw_set(cmc, 'braking_deceleration_flying', float(self.M['braking_flying']))
                cmc.set_movement_mode(unreal.MovementMode.MOVE_FLYING)
                self.flying.add(key)
        except Exception:
            self.err('flying')

    def look_active(self):
        if self.phase in ('damage', 'kill', 'respawned'):
            return True
        plan = self.cfg['shots']['plan'] if self.cfg['shots']['enabled'] else []
        lead = self.cfg['shots']['look_lead_s']
        for s in plan:
            if s['phase'] == self.phase and 'player' in s['kinds'] and s['at'] - lead <= self.pt() <= s['at'] + 0.3:
                return True
        return False

    def steer(self, role, w):
        for pid, p in self.players_in(w).items():
            self.ensure_flying(p)
        pc = bw_local_pc(w)
        pawn = pc.get_controlled_pawn() if pc else None
        if pawn is None:
            return
        pid = bw_pid_of_pawn(pawn)
        if pid is None:
            return
        pl = self.players.setdefault(pid, {'first_pawn_t': self.now})
        loc = bw_vec(pawn.get_actor_location())
        ph = self.phase
        if ph == 'follow':
            mode = 'lane'
        elif ph in ('cut', 'cut_settle', 'damage', 'kill', 'respawn', 'respawned'):
            mode = 'hover'
        else:
            mode = 'hold'
        target = None
        if mode == 'lane':
            target = self.lane_target(pid, loc)
            pl['hold'] = None
        elif mode == 'hover':
            target = pl.get('hover') or pl.get('hold') or loc
        else:
            if pl.get('hold') is None:
                pl['hold'] = loc
            target = pl['hold']
        v = bw_sub(target, loc) if target else None
        if v is not None:
            d = bw_len(v)
            if mode == 'lane':
                if d > 1.0:
                    pawn.add_movement_input(bw_uvec(bw_norm(v)), 1.0, True)
            elif d > self.M['hold_radius']:
                pawn.add_movement_input(bw_uvec(bw_norm(v)), max(0.15, min(1.0, d / 300.0)), True)
        if self.look_active():
            rec = self.own_burrower(role, pid)
            if rec is not None:
                aim = self.bone_world(rec, self.D['aim_bone']) or bw_vec(rec['actor'].get_actor_location())
                cam = unreal.GameplayStatics.get_player_camera_manager(w, 0)
                if cam:
                    pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(cam.get_camera_location(), bw_uvec(aim)))
                if self.phase == 'damage' and role in self.D['fire_roles'] and self.damage.get('firing'):
                    self.fire(w, role)
        elif mode == 'lane' and v is not None and bw_len2d(v) > 1.0:
            yaw = math.degrees(math.atan2(v[1], v[0]))
            pc.set_control_rotation(unreal.Rotator(roll=0.0, pitch=float(self.M['lane_pitch']), yaw=yaw))

    def fire(self, w, role):
        if self.ia is None:
            return
        sub = None
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and lp.get_world() == w:
                    sub = s
                    break
            except Exception:
                continue
        if sub is None:
            if self.due('nosub_' + role, 5.0):
                self.line('WARN', 'no EnhancedInputLocalPlayerSubsystem for the %s world: cannot fire' % role)
            return
        sub.inject_input_vector_for_action(self.ia, unreal.Vector(1, 0, 0), [], [])
        self.damage['shots_injected'] = self.damage.get('shots_injected', 0) + 1

    # ------------------------------------------------------------------ check g (damage)

    def damage_begin(self):
        self.damage = {'t0': self.now, 'firing': bool(self.D['fire_roles']), 'start': {}, 'samples': [], 'method': 'gun', 'fallback_t': None,
                       'bar_start': {}, 'shots_injected': 0}
        for role in ('server', 'client'):
            for rec in self.alive_burrowers(role):
                h, m = self.health(rec['actor'])
                self.damage['start']['%s:%s' % (role, rec['name'])] = {'health': h, 'max': m, 'pid': rec.get('target_pid')}
                self.damage['bar_start']['%s:%s' % (role, rec['name'])] = self.health_bar_percent(rec['actor'])
        self.line('INFO', 'damage: start health %s; firing roles %s' % (self.damage['start'], self.D['fire_roles']))

    def ph_damage(self):
        D = self.damage
        # stop firing once the server health dropped enough (so the gun does not kill it before KillAll)
        drops = self.health_drops('server')
        if D['firing'] and drops and max(drops.values()) >= self.D['stop_after_drop']:
            D['firing'] = False
            self.event('stop_firing', drops=drops)
        if self.pt() < self.T['damage_s']:
            return
        if D['fallback_t'] is None:
            if not drops or max(drops.values()) < self.TH['health_min_drop']:
                D['method'] = 'ge_fallback'
                D['firing'] = False
                D['fallback_t'] = self.now
                self.apply_fallback_damage()
                return
            D['fallback_t'] = -1.0
        if D['fallback_t'] > 0 and self.now - D['fallback_t'] < self.D['fallback_wait_s']:
            return
        self.eval_damage()
        self.kill_begin()

    def health_drops(self, role):
        out = {}
        for rec in self.alive_burrowers(role):
            k = '%s:%s' % (role, rec['name'])
            s = self.damage['start'].get(k)
            if not s or s['health'] is None:
                continue
            h, m = self.health(rec['actor'])
            if h is not None:
                out[k] = round(s['health'] - h, 2)
        return out

    def apply_fallback_damage(self):
        """No drop from the gun: the project's damage GE with SetByCaller, from the target player's ASC (server)."""
        try:
            ge = unreal.load_class(None, self.D['fallback_ge'])
            tag = unreal.GameplayTag()
            tag.import_text('(TagName="%s")' % self.D['set_by_caller_tag'])
            sp = self.players_in(self.sw)
            for rec in self.alive_burrowers('server'):
                b = rec['actor']
                h, m = self.health(b)
                dmg = float(self.D['fallback_damage'])
                if h is not None:
                    dmg = max(0.0, min(dmg, h - 1.0))
                src_pawn = sp.get(rec.get('target_pid')) or (list(sp.values())[0] if sp else None)
                src = unreal.AbilitySystemLibrary.get_ability_system_component(src_pawn) if src_pawn else None
                dst = unreal.AbilitySystemLibrary.get_ability_system_component(b)
                if src is None or dst is None or ge is None:
                    self.line('WARN', 'fallback damage: missing source ASC %s / target ASC %s / GE %s' % (src, dst, ge))
                    continue
                ctx = src.make_effect_context()
                spec = src.make_outgoing_spec(ge, 1.0, ctx)
                spec = unreal.AbilitySystemLibrary.assign_tag_set_by_caller_magnitude(spec, tag, dmg)
                src.apply_gameplay_effect_spec_to_target(spec, dst)
                self.event('fallback_damage', burrower=rec['name'], damage=dmg, health_before=h)
                self.line('WARN', 'no health drop from the gun after %.0f s: applied %s (%.1f) to %s from Python' % (self.T['damage_s'], self.D['fallback_ge'], dmg, rec['name']))
        except Exception:
            self.err('fallback_damage')

    def eval_damage(self):
        D = self.damage
        res = {'method': D['method'], 'shots_injected': D.get('shots_injected', 0), 'start': D['start'], 'end': {}, 'bar_start': D['bar_start'], 'bar_end': {},
               'gun_hits_in_log': (self.R['log_scan'].get('hit_burrower') or {}).get('count', 0), 'series': D['samples'][-40:]}
        for role in ('server', 'client'):
            for rec in self.alive_burrowers(role):
                k = '%s:%s' % (role, rec['name'])
                h, m = self.health(rec['actor'])
                res['end'][k] = {'health': h, 'max': m}
                res['bar_end'][k] = self.health_bar_percent(rec['actor'])
        sd = {k: round((D['start'][k]['health'] or 0) - (v['health'] or 0), 2) for k, v in res['end'].items() if k in D['start'] and D['start'][k]['health'] is not None and v['health'] is not None}
        res['drop'] = sd
        sdrop = [v for k, v in sd.items() if k.startswith('server:')]
        cdrop = [v for k, v in sd.items() if k.startswith('client:')]
        ok_s = bool(sdrop) and max(sdrop) >= self.TH['health_min_drop']
        ok_c = bool(cdrop) and max(cdrop) >= self.TH['health_min_drop']
        bars = ['%s %s->%s' % (k, res['bar_start'].get(k), v) for k, v in res['bar_end'].items()]
        if ok_s and ok_c:
            st = 'PASS' if D['method'] == 'gun' else 'WARN'
            msg = 'health dropped by %s on the server and %s on the client via %s%s; health bars %s' % (
                max(sdrop), max(cdrop), D['method'], '' if D['method'] == 'gun' else ' (THE GUN DID NOT HIT: aim/collision?)', bars)
        else:
            st = 'FAIL'
            msg = 'health drop server %s, client %s (method %s, %d gun hits in the log); start %s end %s' % (sdrop, cdrop, D['method'], res['gun_hits_in_log'], D['start'], res['end'])
        self.check('g_damage', st, msg, res)

    # ------------------------------------------------------------------ check h (death)

    def kill_begin(self):
        if self.cfg['spawn_mode'] == 'spawnnow' and self.cfg['enable_before_kill']:
            try:
                bw_set(bw_settings_cdo(), 'bEnabled', True)
                self.R['settings_at_kill'] = bw_read_settings(bw_settings_cdo())
                self.line('INFO', 'BurrowerSettings.bEnabled = True (memory) so the respawn countdown runs')
            except Exception:
                self.err('enable')
        self.kill = {'t0': self.now, 'recs': {}, 'old': {'server': set(self.burrowers['server'].keys()), 'client': set(self.burrowers['client'].keys())}}
        for role in ('server', 'client'):
            for rec in self.alive_burrowers(role):
                b = rec['actor']
                try:
                    base = {n: self.bone_world(rec, n) for n in self.B['body']}
                    self.kill['recs']['%s:%s' % (role, rec['name'])] = {'rec': rec, 'role': role, 'pid': rec.get('target_pid'), 'actor0': bw_vec(b.get_actor_location()),
                                                                         'bones0': base, 'dead_t': None, 'anim_dead_t': None, 'max_bone_move': 0.0,
                                                                         'max_actor_move': 0.0, 'z_drop': 0.0, 'n': 0, 'last_bones': base}
                except Exception:
                    self.err('kill_base')
        self.set_phase('kill')
        self.console('Aura.Burrower.KillAll')

    def ph_kill(self):
        K = self.kill
        if self.due('ragdoll', self.S['ragdoll_dt']):
            for k, e in K['recs'].items():
                rec = e['rec']
                b = rec.get('actor')
                if not bw_valid(b):
                    continue
                try:
                    if e['dead_t'] is None and b.is_burrower_dead():
                        e['dead_t'] = self.now - K['t0']
                    ai = rec['mesh'].get_anim_instance() if rec.get('mesh') else None
                    if e['anim_dead_t'] is None and ai is not None and bw_get(ai, 'is_dead'):
                        e['anim_dead_t'] = self.now - K['t0']
                    e['max_actor_move'] = max(e['max_actor_move'], bw_len(bw_sub(bw_vec(b.get_actor_location()), e['actor0'])))
                    zs = []
                    for n, p0 in e['bones0'].items():
                        p = self.bone_world(rec, n)
                        if p is None or p0 is None:
                            continue
                        e['max_bone_move'] = max(e['max_bone_move'], bw_len(bw_sub(p, p0)))
                        zs.append(p0[2] - p[2])
                    if zs:
                        e['z_drop'] = round(sum(zs) / len(zs), 1)
                    e['n'] += 1
                except Exception:
                    self.err('ragdoll_sample')
        if self.pt() >= self.T['ragdoll_s']:
            self.eval_death()
            self.respawn = {'t0': K['t0'], 'by_pid': {}, 'client_seen': {}}
            self.set_phase('respawn')

    def eval_death(self):
        res = {}
        ok = True
        notes = []
        for k, e in self.kill['recs'].items():
            role = e['role']
            wait = self.TH['dead_wait_server_s'] if role == 'server' else self.TH['dead_wait_client_s']
            r = {'pid': e['pid'], 'dead_after_s': bw_r(e['dead_t'], 2), 'anim_dead_after_s': bw_r(e['anim_dead_t'], 2),
                 'max_bone_move_cm': round(e['max_bone_move'], 1), 'max_actor_move_cm': round(e['max_actor_move'], 1), 'mean_bone_z_drop_cm': e['z_drop'], 'samples': e['n']}
            good = (e['dead_t'] is not None and e['dead_t'] <= wait and e['max_bone_move'] >= self.TH['ragdoll_min_bone_move_cm']
                    and e['max_actor_move'] <= self.TH['ragdoll_max_actor_move_cm'])
            r['ok'] = good
            if not good:
                ok = False
                notes.append('%s: dead after %s s, bones moved %.0f cm, actor moved %.0f cm, anim bIsDead after %s s' % (k, r['dead_after_s'], e['max_bone_move'], e['max_actor_move'], r['anim_dead_after_s']))
            res[k] = r
        try:
            res['use_mesh_ragdoll_fallback'] = (self.R.get('burrower_bp') or {}).get('use_mesh_ragdoll_fallback')
        except Exception:
            pass
        if not self.kill['recs']:
            self.check('h_death', 'FAIL', 'no living Burrower to kill', res)
            return
        s = ['%s dead %.2f s, bones %.0f cm, actor %.0f cm' % (k, v['dead_after_s'] or -1, v['max_bone_move_cm'], v['max_actor_move_cm']) for k, v in res.items() if isinstance(v, dict)]
        self.check('h_death', 'PASS' if ok else 'FAIL', '; '.join(s) if ok else '; '.join(notes), res)

    # ------------------------------------------------------------------ check i (respawn)

    def ph_respawn(self):
        RS = self.respawn
        si = float((self.R.get('settings_during') or {}).get('SpawnInterval', 8.0))
        for role in ('server', 'client'):
            for rec in self.alive_burrowers(role):
                if rec['key'] in self.kill['old'][role]:
                    continue
                pid = self.target_pid(rec['actor'])
                if role == 'server' and pid not in RS['by_pid']:
                    RS['by_pid'][pid] = {'burrower': rec['name'], 'after_kill_s': round(self.now - RS['t0'], 2)}
                    self.event('respawned', pid=pid, burrower=rec['name'], after_kill_s=RS['by_pid'][pid]['after_kill_s'])
                    self.line('INFO', 'new Burrower %s for player %s, %.2f s after KillAll' % (rec['name'], pid, self.now - RS['t0']))
                elif role == 'client' and pid not in RS['client_seen']:
                    RS['client_seen'][pid] = round(self.now - RS['t0'], 2)
        pids = list(self.players.keys())
        all_s = all(p in RS['by_pid'] for p in pids)
        all_c = all(p in RS['client_seen'] for p in pids) or self.cw is None
        late = self.now - RS['t0'] > si + self.TH['respawn_tol_late_s'] + self.T['respawn_margin_s']
        if (all_s and all_c and self.now - RS['t0'] > si) or late:
            res = {'SpawnInterval': si, 'server': RS['by_pid'], 'client_seen_after_s': RS['client_seen'],
                   'settings_at_kill': self.R.get('settings_at_kill')}
            ok = all_s and all_c
            notes = []
            for p in pids:
                e = RS['by_pid'].get(p)
                if not e:
                    notes.append('player %s: no new Burrower within %.0f s' % (p, self.now - RS['t0']))
                    ok = False
                    continue
                if not (si - self.TH['respawn_tol_early_s'] <= e['after_kill_s'] <= si + self.TH['respawn_tol_late_s']):
                    notes.append('player %s: new one after %.2f s (SpawnInterval %.1f)' % (p, e['after_kill_s'], si))
                    ok = False
            if not all_c:
                notes.append('client did not see all new Burrowers: %s' % RS['client_seen'])
            s = ['p%s after %.2f s' % (p, e['after_kill_s']) for p, e in RS['by_pid'].items()]
            self.check('i_respawn', 'PASS' if ok else 'FAIL', ('new Burrower per player after SpawnInterval %.1f s: %s' % (si, ', '.join(s))) if ok else '; '.join(notes), res)
            if RS['by_pid']:
                self.set_phase('respawned')
            else:
                self.finish('ok (no respawn)')

    # ------------------------------------------------------------------ sampling

    def sample(self):
        ph = self.phase
        roles = [('server', self.sw)] + ([('client', self.cw)] if self.cw is not None else [])
        # distances (b): from the spawn to the end of the follow phase
        if ph in ('spawn', 'follow') and self.due('dist', self.S['dist_dt']):
            for role, w in roles:
                pawns = self.players_in(w)
                for rec in self.alive_burrowers(role):
                    try:
                        b = rec['actor']
                        pid = self.target_pid(b)
                        rec['target_pid'] = pid
                        p = pawns.get(pid)
                        if p is None:
                            continue
                        bl = bw_vec(b.get_actor_location())
                        d = bw_len(bw_sub(bl, bw_vec(p.get_actor_location())))
                        tr = rec['dist'][-1][2] if rec['dist'] else 0.0
                        if rec.get('last_loc') is not None:
                            tr += bw_len(bw_sub(bl, rec['last_loc']))
                        rec['last_loc'] = bl
                        rec['dist'].append((self.now, d, tr))
                    except Exception:
                        self.err('dist')
        # poses (c, f) during the follow phase; rotor (d) every frame inside its window
        if ph == 'follow':
            rw0 = self.S['rotor_window_start']
            in_rotor = rw0 <= self.pt() <= rw0 + self.S['rotor_window_s']
            pose_due = self.due('pose', self.S['pose_dt'])
            for role, w in roles:
                for rec in self.alive_burrowers(role):
                    if rec.get('mesh') is None:
                        continue
                    try:
                        if in_rotor and self.B['rotor'] in rec['bones']:
                            t, q = self.comp_xf(rec, self.B['rotor'])
                            ai = rec['mesh'].get_anim_instance()
                            ang = float(bw_get(ai, 'rotor_angle_deg')) if ai is not None and bw_get(ai, 'rotor_angle_deg') is not None else None
                            rec['rotor'].append((self.now, t, q, ang))
                        if pose_due:
                            self.sample_pose(rec)
                    except Exception:
                        self.err('pose')
        # tiles (e) from the spawn until the damage phase
        if ph in ('spawn', 'follow', 'cut', 'cut_settle') and self.due('tiles', self.S['tile_dt']):
            for role, w in roles:
                self.tiles_step(role, w)
            if ph == 'cut':
                self.cut_diag()
        # health (g)
        if ph == 'damage' and self.due('health', self.S['health_dt']):
            row = {'t': round(self.pt(), 2)}
            for role, w in roles:
                for rec in self.alive_burrowers(role):
                    row['%s:%s' % (role, rec['name'])] = self.health(rec['actor'])[0]
            self.damage['samples'].append(row)
        if self.due('summary', self.S['summary_dt']):
            self.summary(roles)

    def sample_pose(self, rec):
        names = rec['bones']
        X = {}
        for n in names:
            X[n] = self.comp_xf(rec, n)
        body = self.B['body']
        ai = rec['mesh'].get_anim_instance()
        amp = bw_get(ai, 'wave_amplitude_deg') if ai is not None else None
        wt = bw_get(ai, 'wave_time') if ai is not None else None
        if body[0] in X and body[4] in X:
            j0 = X[body[0]][0]
            rec['lateral'].append((self.now, X[body[2]][0][1] - j0[1] if body[2] in X else None,
                                   X[body[3]][0][1] - j0[1] if body[3] in X else None, X[body[4]][0][1] - j0[1],
                                   float(amp) if amp is not None else None, float(wt) if wt is not None else None))
        anc = self.B['pipe_anchor']
        if anc not in X:
            return
        ta, qa = X[anc]
        qai = bw_qconj(qa)
        rest_a = rec['rest'].get(anc)
        for ch in (self.rig or {}).get('chains', []):
            b01, bend = ch['bones'][0], ch['end_bone']
            if b01 not in X or bend not in X:
                continue
            p = rec['pipes'].get(ch['name'])
            if p is None:
                r01 = rec['rest'].get(b01)
                rend = rec['rest'].get(bend)
                if rest_a and r01 and rend:
                    rest01 = bw_len(bw_sub(r01[0], rest_a[0]))
                    restend = bw_len(bw_sub(rend[0], rest_a[0]))
                    qri = bw_qconj(rest_a[1])
                    l01 = bw_qrot(qri, bw_sub(r01[0], rest_a[0]))
                    lend = bw_qrot(qri, bw_sub(rend[0], rest_a[0]))
                else:   # no ref pose: the first live sample is the rest
                    rest01 = bw_len(bw_sub(X[b01][0], ta))
                    restend = bw_len(bw_sub(X[bend][0], ta))
                    l01 = bw_qrot(qai, bw_sub(X[b01][0], ta))
                    lend = bw_qrot(qai, bw_sub(X[bend][0], ta))
                p = {'rest01': rest01, 'restend': restend, 'l01': l01, 'lend': lend, 'drift01': 0.0, 'driftend': 0.0, 'loc01': 0.0, 'locend': 0.0,
                     'mid': {m: BwStat() for m in self.pipe_mids(ch) if m in X}, 'n': 0}
                rec['pipes'][ch['name']] = p
            p['n'] += 1
            p['drift01'] = max(p['drift01'], abs(bw_len(bw_sub(X[b01][0], ta)) - p['rest01']))
            p['driftend'] = max(p['driftend'], abs(bw_len(bw_sub(X[bend][0], ta)) - p['restend']))
            p['loc01'] = max(p['loc01'], bw_len(bw_sub(bw_qrot(qai, bw_sub(X[b01][0], ta)), p['l01'])))
            p['locend'] = max(p['locend'], bw_len(bw_sub(bw_qrot(qai, bw_sub(X[bend][0], ta)), p['lend'])))
            for m, stat in p['mid'].items():
                if m in X:
                    stat.add(bw_qrot(qai, bw_sub(X[m][0], ta)))

    def cut_diag(self):
        """Cut phase geometry: rotor box vs the hover point and the tile tops under it (server)."""
        try:
            d = self.R['series'].setdefault('cut_diag', [])
            if len(d) > 60:
                return
            sp = self.players_in(self.sw)
            for rec in self.alive_burrowers('server'):
                rb = rec.get('rotor_box')
                if rb is None:
                    continue
                c = bw_vec(rb.get_world_location())
                pid = self.target_pid(rec['actor'])
                p = sp.get(pid)
                hv = self.players.get(pid, {}).get('hover')
                d.append({'t': round(self.pt(), 1), 'burrower': rec['name'], 'rotor': bw_r(c), 'extent': bw_r(rec['rotor_extent']),
                          'pawn': bw_r(bw_vec(p.get_actor_location())) if p else None, 'hover': bw_r(hv),
                          'rotor_to_hover_h': bw_r(bw_len2d(bw_sub(c, hv))) if hv else None,
                          'box_bottom_minus_tile_top': bw_r(c[2] - rec['rotor_extent'][2] - (hv[2] - self.M['cut_hover_z'])) if hv else None})
        except Exception:
            self.err('cut_diag')

    def summary(self, roles):
        s = {'t': round(self.now, 1), 'phase': self.phase, 'fps_est': self.fps, 'worlds': {}}
        for role, w in roles:
            info = {'burrowers': []}
            pawns = self.players_in(w)
            info['pawns'] = {str(k): bw_r(bw_vec(v.get_actor_location()), 0) for k, v in pawns.items() if bw_valid(v)}
            for rec in self.burrowers[role].values():
                b = rec.get('actor')
                if rec.get('gone') or not bw_valid(b):
                    continue
                try:
                    e = {'name': rec['name'], 'pid': rec.get('target_pid'), 'loc': bw_r(bw_vec(b.get_actor_location()), 0),
                         'speed': round(bw_len(bw_vec(b.get_velocity())), 0), 'dead': bool(b.is_burrower_dead()), 'health': self.health(b)[0]}
                    ai = rec['mesh'].get_anim_instance() if rec.get('mesh') else None
                    if ai is not None:
                        e['anim'] = {'rotor': bw_r(bw_get(ai, 'rotor_angle_deg')), 'spin': bw_r(bw_get(ai, 'rotor_spin_speed')),
                                     'wave_t': bw_r(bw_get(ai, 'wave_time'), 3), 'amp': bw_r(bw_get(ai, 'wave_amplitude_deg'), 2),
                                     'dead': bw_get(ai, 'is_dead')}
                    else:
                        e['anim'] = None
                    info['burrowers'].append(e)
                except Exception:
                    continue
            s['worlds'][role] = info
        if len(self.R['samples']) < 400:
            self.R['samples'].append(s)

    # ------------------------------------------------------------------ shots

    def shots_step(self):
        if not self.cfg['shots']['enabled']:
            return
        for i, s in enumerate(self.cfg['shots']['plan']):
            if i in self.shot_done or s['phase'] != self.phase or self.pt() < s['at']:
                continue
            self.shot_done.add(i)
            out = {'label': s['label'], 't': round(self.now, 2), 'phase': self.phase, 'files': []}
            for role, w in (('server', self.sw), ('client', self.cw)):
                if w is None:
                    continue
                pc = bw_local_pc(w)
                pawn = pc.get_controlled_pawn() if pc else None
                pid = bw_pid_of_pawn(pawn) if pawn else None
                rec = self.own_burrower(role, pid)
                if rec is None:
                    # after KillAll the dead one is the subject
                    for r in self.burrowers[role].values():
                        if not r.get('gone') and bw_valid(r.get('actor')):
                            rec = r
                            break
                for kind in s['kinds']:
                    try:
                        f = self.capture(role, w, kind, rec, '%s_%s_%s' % (s['label'], kind, role))
                        if f:
                            out['files'].append(f)
                    except Exception:
                        self.err('capture')
            if self.cfg['shots']['xgrab']:
                try:
                    with open(os.path.join(self.xgrab_dir, '%s_%s.req' % (self.cfg['run_name'], s['label'])), 'w') as f:
                        f.write(self.out_dir + '/pie_shots/' + self.cfg['run_name'] + '\n')
                    out['xgrab'] = True
                except Exception:
                    self.err('xgrab')
            self.R['shots'].append(out)
            self.line('INFO', 'shot %s: %s' % (s['label'], out['files']))

    def capture(self, role, w, kind, rec, name):
        if self.captures >= self.cfg['shots']['max_captures'] or role in self.cap_dead:
            return None
        frm = None
        to = None
        fov = 70.0
        if kind == 'player':
            cam = unreal.GameplayStatics.get_player_camera_manager(w, 0)
            if not cam:
                return None
            loc = cam.get_camera_location()
            rot = cam.get_camera_rotation()
            fov = cam.get_fov_angle()
        else:
            if rec is None or not bw_valid(rec.get('actor')):
                return None
            b = rec['actor']
            fwd = bw_vec(b.get_actor_forward_vector())
            right = bw_vec(b.get_actor_right_vector())
            rotor = bw_vec(rec['rotor_box'].get_world_location()) if rec.get('rotor_box') else bw_vec(b.get_actor_location())
            mid = self.bone_world(rec, 'J2_Midbody') or bw_add(bw_vec(b.get_actor_location()), bw_mul(fwd, -830.0))
            if kind == 'side':
                frm, to, fov = bw_add(bw_add(mid, bw_mul(right, 2800.0)), (0.0, 0.0, 900.0)), mid, 75.0
            elif kind == 'rotor':
                frm, to, fov = bw_add(bw_add(bw_add(rotor, bw_mul(fwd, 650.0)), bw_mul(right, 450.0)), (0.0, 0.0, 250.0)), rotor, 60.0
            elif kind == 'top':
                frm, to, fov = bw_add(bw_add(rotor, bw_mul(fwd, -300.0)), (0.0, 0.0, 2200.0)), bw_add(rotor, bw_mul(fwd, 200.0)), 70.0
            else:
                return None
            loc = bw_uvec(frm)
            rot = unreal.MathLibrary.find_look_at_rotation(loc, bw_uvec(to))
        key = w.get_path_name()
        if key not in self.cap_res:
            caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.SceneCapture2D) if BW_TEMP_LABEL in a.get_actor_label()]
            if not caps:
                self.cap_dead.add(role)
                self.line('WARN', 'no %s actor in the %s world: scene captures off there' % (BW_TEMP_LABEL, role))
                return None
            try:
                rt = unreal.RenderingLibrary.create_render_target2d(w, int(self.cfg['shots']['width']), int(self.cfg['shots']['height']), unreal.TextureRenderTargetFormat.RTF_RGBA8)
                c = caps[0].capture_component2d
                c.set_editor_property('texture_target', rt)
                c.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                c.set_editor_property('capture_every_frame', False)
                c.set_editor_property('capture_on_movement', False)
                c.set_editor_property('always_persist_rendering_state', True)
                self.cap_res[key] = (caps[0], c, rt)
            except Exception:
                # never retry (leaked render targets crashed Vulkan before)
                self.cap_dead.add(role)
                self.err('capture_setup')
                return None
        a, c, rt = self.cap_res[key]
        c.set_editor_property('fov_angle', float(fov))
        a.set_actor_location_and_rotation(loc, rot, False, True)
        c.capture_scene()
        # ExportRenderTarget writes PNG data for RGBA8 but adds no extension (KismetRenderingLibrary.cpp:231-290)
        unreal.RenderingLibrary.export_render_target(w, rt, self.shot_dir, name + '.png')
        self.captures += 1
        return os.path.join(self.shot_dir, name + '.png')


# =====================================================================================================================
# Entry points
# =====================================================================================================================

def bw_load_config(path):
    cfg = BW_DEFAULTS
    if path and os.path.isfile(path):
        with open(path) as f:
            cfg = bw_merge(BW_DEFAULTS, json.load(f))
    return json.loads(json.dumps(cfg))


def bw_main():
    # popped, so a wrapper's choice does not stick in the inbox's shared namespace for the next run
    path = globals().pop('BW_CONFIG', None) or BW_DEFAULT_CONFIG
    preflight_only = bool(globals().pop('BW_PREFLIGHT_ONLY', False))
    if not os.path.isfile(path):
        print('WARN: config %s not found: built-in defaults (BW_DEFAULTS) are used' % path)
    try:
        cfg = bw_load_config(path)
    except Exception as e:
        print('FAIL: config %s does not parse: %r' % (path, e))
        return
    prev = globals().get('BW_RUN')
    if prev is not None and not prev.ended:
        print('FAIL: a Burrower PIE run (%s) is still active (phase %s): wait for it or run bw_pie_cleanup.py first' % (prev.cfg['run_name'], prev.phase))
        return
    run = BwRun(cfg)
    if preflight_only:
        run.phase = 'preflight'
        ok = run.preflight(arm=False)
        print('%s: preflight %s (nothing changed, PIE not started)' % ('PASS' if ok else 'FAIL', 'ok' if ok else 'failed'))
        return
    print('INFO: config %s' % path)
    globals()['BW_RUN'] = run
    if not run.arm():
        run.ended = True


if not globals().get('BW_NO_MAIN'):
    bw_main()
