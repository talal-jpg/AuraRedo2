# as_45_pie_mp.py - multiplayer PIE test of the drivable airship on L_AirshipTest: Play As Listen Server with 2 players
# (the host + 1 client, one process; set in the ini with the editor closed: Docs/Airship/scripts/harness/set_play_mode.sh
# listen 2, and back with set_play_mode.sh standalone), fixed 30 fps game time. Session 2026-11-22 (multiplayer step).
# Run (L_AirshipTest open, no PIE): inbox.sh 45 Docs/Airship/scripts/ue/as_45_pie_mp.py 60; status: inbox.sh 45s
# Docs/Airship/scripts/ue/as_45s_mp_status.py; X grabs: harness/xgrab_mp.sh running in the background.
# It arms a frame-by-frame state machine (Slate post-tick callback) that drives BOTH PIE worlds from the editor's Python:
#  server world (UEDPIE_0): the host's PC / character, the server copies of the client's PC / character and the ships
#  client world (UEDPIE_1): the client's PC / character / ship copies, its Enhanced Input subsystem
# The client only uses its own machine's paths: F / fire / exit / throttle / steer are injected into the CLIENT's Enhanced
# Input subsystem (IA_AirshipBoard -> UAirshipPilotComponent::ServerRequestBoard, IA_AirshipFire -> ServerFireCannons,
# IA_AirshipExit -> ServerRequestExit, IA_AirshipThrottle/Steer -> GatherLocalInput -> ServerSetPilotInput), and the flight
# schedules call DebugSetInput on the CLIENT's copy of its ship (since 2026-11-22 it replaces the keys on the pilot's
# machine and goes through ServerSetPilotInput). Console commands that are server-only run in the server world.
# Phases (game seconds): settle 4 | board_far 2 (F out of range: refused) | board_tp 3 (client teleported onto the deck) |
#  board 3 (F) | hover 4 | cannons 9 (c) | gun 7 (b: the host shoots the ship with GA_GunShoot) | keys 4 (injected
#  throttle/steer) | fly0 14 (a, no lag) | lag_on 3 (Net PktLag on both worlds) | fly1 14 (a, lag) | lag_off 3 |
#  c_exit 4 (F) | c_board2 3 (F) | kill 12 (d) | spawn2 3 (Aura.Airship.Spawn) | deck2 4 (client + host onto ship 2's
#  deck) | host_board 3 (host's F) | host_fly 14 (e: the host flies, the client rides on the deck)
# Scheme (since 2026-11-23): AS45_SCHEME (default 0 = Classic, the v1 checks) on the server's ship in settle and, since
# the follow-up (F-E), on ship 2 the moment spawn2 has made it (it used to start in the pawn's default, Point & Fly).
# Results: Saved/Airship/mp/mp_result.json, mp_report.txt, mp_log.txt; captures Saved/Airship/captures/mp/;
# X grabs Saved/Airship/mp/xgrab/. In memory only, restored at the end: UnrealEdEngine fixed frame rate 30,
# BurrowerSettings.bEnabled False, p.NetShowCorrections 1, Net PktLag. One TEMP_AS_Capture SceneCapture2D in the editor
# level (removed after PIE; the map is never saved). The user's own Play is never stopped.
import json, math, os, time, traceback  # unreal = inbox namespace

AS45_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as45_src = open(AS45_AS30).read()
exec(compile(_as45_src[:_as45_src.index('\nclass AsRun')], AS45_AS30, 'exec'), globals())   # maths + tl_get/tl_set/gp/valid/parse_struct

AS45_VERSION = 'as_45_pie_mp 2026-11-23'
MP = os.path.join(OUT, 'mp')
CAPS = os.path.join(OUT, 'captures', 'mp')
XG = os.path.join(MP, 'xgrab')
IA = '/Game/Assets/MyShip/Drivable/Input/'
IA_LMB_PATH = '/Game/Level/PlayerInput/IA_LMB'
MAX_CAPS = 30
GROUND_TOP = -19950.0
LAG_GAME_MS = 100.0           # one-way lag wanted in GAME time; PktLag is real time (FPlatformTime), scaled by the real fps
ANIM_VARS = ['WheelAngleDeg', 'TurbineYawDeg_L', 'TurbineYawDeg_R', 'RudderDeg', 'RotorAngleDeg_L', 'ThrustAlpha_FL',
             'NozzlePitchDeg_FL', 'NozzleRollDeg_FL', 'CannonRecoilCm_L1', 'CannonRecoilCm_L2', 'CannonRecoilCm_R1',
             'CannonRecoilCm_R2', 'CannonYawDeg_L1', 'CannonYawDeg_R1', 'bIsDead', 'DeathTime']
TELE_KEYS = ['SpeedMS', 'ForwardSpeedMS', 'LateralSpeedMS', 'YawRateDegS', 'VerticalSpeedMS', 'RollDeg', 'PitchDeg', 'YawDeg',
             'AltitudeM', 'HoldAltitudeM', 'Throttle', 'Steer', 'Lift', 'Boost', 'bBraking', 'Health', 'MaxHealth', 'bHasPilot',
             'bIsDead']
BREAKOFF = ['Thruster_FL', 'Thruster_RR', 'Turbine_L', 'Rudder', 'SearchLight_FwdC']
PHASES = [('settle', 4.0), ('board_far', 2.0), ('board_tp', 3.0), ('board', 3.0), ('hover', 4.0), ('cannons', 9.0),
          ('gun', 7.0), ('keys', 4.0), ('fly0', 14.0), ('lag_on', 3.0), ('fly1', 14.0), ('lag_off', 3.0), ('c_exit', 4.0),
          ('c_board2', 3.0), ('kill', 12.0), ('spawn2', 3.0), ('deck2', 4.0), ('host_board', 3.0), ('host_fly', 14.0)]
PER_FRAME = ('hover', 'cannons', 'gun', 'keys', 'fly0', 'lag_on', 'fly1', 'lag_off', 'c_exit', 'c_board2', 'kill', 'deck2',
             'host_board', 'host_fly')
NEUTRAL = (0.0, 0.0, 0.0, 0.0, False, False)
BRAKE = (0.0, 0.0, 0.0, 0.0, False, True)
# client flight schedule (phase seconds -> DebugSetInput on the CLIENT's ship); edges E1..E4 are measured
FLY = [(0.0, 'start', NEUTRAL), (0.5, 'E1_throttle', (1.0, 0.0, 0.0, 0.0, False, False)),
       (5.0, 'E2_steer_right', (1.0, 1.0, 0.0, 0.0, False, False)), (9.0, 'E3_steer_left', (1.0, -1.0, 0.0, 0.0, False, False)),
       (11.0, 'E4_brake', BRAKE), (13.5, 'neutral', NEUTRAL)]
# host flight schedule on ship 2 (DebugSetInput on the HOST's ship, server world)
HOST_FLY = [(0.0, 'neutral', NEUTRAL), (4.0, 'throttle', (0.5, 0.0, 0.0, 0.0, False, False)),
            (9.0, 'turn', (0.5, 0.6, 0.0, 0.0, False, False)), (12.0, 'brake', BRAKE)]


def en(x):
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


def same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def trace_loc(res):
    """hit location of a K2_LineTraceComponent result (None on a miss), whichever way the bool return is wrapped"""
    if not res:
        return None
    if isinstance(res, tuple):
        if isinstance(res[0], bool) and not res[0]:
            return None
        for x in res:
            if isinstance(x, unreal.Vector):
                return v3(x)
    return None


def qang(a, b):
    """angle (deg) between two unit quats [x,y,z,w]"""
    d = abs(sum(a[i] * b[i] for i in range(4)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, d))))


def stats(xs):
    if not xs:
        return None
    s = sorted(xs)
    return {'n': len(s), 'mean': r(sum(s) / len(s), 2), 'p95': r(s[min(len(s) - 1, int(0.95 * len(s)))], 2), 'max': r(s[-1], 2)}


class MpRun(object):
    def __init__(self):
        self.R = {'version': AS45_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': {},
                  'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'xgrabs': [], 'done': False, 'mp': {}}
        self.orig = {}
        self.handle = None
        self.phase = 'arming'
        self.pi = -1
        self.p_t0 = 0.0
        self.now = 0.0
        self.t_world0 = None
        self.wall0 = time.time()
        self.last_sample = -1.0
        self.last_write = 0.0
        self.D = {}
        self.sw = self.cw = None
        self.hpc = self.rpc = self.cpc = None
        self.hchar = self.cchar_s = self.cchar_c = self.hchar_c = None
        self.ship_s = self.ship_c = None
        self.ship2_s = self.ship2_c = None
        self.sub_s = self.sub_c = None
        self.capres = {}
        self.cap_dead = {}
        self.ncap = 0
        self.balls = {'server': {}, 'client': {}}
        self.rest = {'server': {}, 'client': {}}
        self.log_file = find_log()
        self.log_off = os.path.getsize(self.log_file) if self.log_file else 0
        self.log_marks = []
        self.user_play = False
        self.frames = 0
        self.fps_mark = None
        self.act = {}
        self.attrs = {}
        for n in ('Health', 'Mana', 'MaxHealth'):
            a = unreal.GameplayAttribute()
            a.import_text('(AttributeName="%s",Attribute=/Script/Aura.MyAttributeSet:%s,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")' % (n, n))
            self.attrs[n] = a

    # ---------------------------------------------------------------- output
    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.phase, msg)
        self.R['lines'].append(s)
        try:
            with open(os.path.join(MP, 'mp_log.txt'), 'a') as f:
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

    def write(self, force=False):
        # Forced only (arm, every phase end, the end): a big dump stalls the frame, and with Net PktLag (real time) a
        # stall in a flight phase would bunch up the lagged packets
        if not force:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        try:
            with open(os.path.join(MP, 'mp_result.json'), 'w') as f:
                json.dump(self.R, f, default=str)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- arm / restore
    def arm(self):
        os.makedirs(MP, exist_ok=True)
        os.makedirs(CAPS, exist_ok=True)
        os.makedirs(XG, exist_ok=True)
        with open(os.path.join(MP, 'mp_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s\n' % (AS45_VERSION, self.R['armed_utc']))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s' % (ew.get_path_name(), MAP_NAME))
            return False
        ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
        self.R['play_settings'] = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
        if 'ListenServer' not in str(self.R['play_settings'].get('PlayNetMode')) or int(self.R['play_settings'].get('PlayNumberOfClients', 0)) != 2:
            self.line('FAIL', 'play settings %s: want PIE_ListenServer, 2 players (set_play_mode.sh listen 2 with the editor closed)' % self.R['play_settings'])
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 5 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        try:
            bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            self.orig['burrower_enabled'] = bool(bcdo.get_editor_property('bEnabled'))
            bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('burrower_settings')
        for n in ('IA_AirshipBoard', 'IA_AirshipFire', 'IA_AirshipExit', 'IA_AirshipThrottle', 'IA_AirshipSteer'):
            self.act[n] = unreal.load_asset(IA + n)
        self.act['IA_LMB'] = unreal.load_asset(IA_LMB_PATH)
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP):
                    eas.destroy_actor(a)
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, -6000, 3000))
            cap.set_actor_label(TEMP)
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
        except Exception:  # noqa: BLE001
            self.err('temp_capture')
        with open(os.path.join(MP, 'mp_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        self.log_mark('arm')
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed; listen-server PIE requested (%s)' % self.R['play_settings'])
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
            if 'burrower_enabled' in self.orig:
                bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
                bcdo.set_editor_property('bEnabled', self.orig['burrower_enabled'], unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_burrower')
        try:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            unreal.SystemLibrary.execute_console_command(ew, 'p.NetShowCorrections 0')
        except Exception:  # noqa: BLE001
            self.err('restore_cvar')

    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP):
                    eas.destroy_actor(a)
            self.line('INFO', 'removed %s from the editor level' % TEMP)
        except Exception:  # noqa: BLE001
            self.err('remove_temp')

    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        for s in (self.ship_c, self.ship2_s, self.ship_s):
            try:
                if valid(s):
                    s.debug_clear_input()
            except Exception:  # noqa: BLE001
                pass
        for w in (self.sw, self.cw):
            try:
                if w is not None:
                    unreal.SystemLibrary.execute_console_command(w, 'Net PktLag=0')
            except Exception:  # noqa: BLE001
                pass
        self.log_mark('end')
        self.scan_log()
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
        write_mp_report(self.R)
        self.line('INFO', 'done; results in mp/mp_result.json / mp/mp_report.txt')

    # ---------------------------------------------------------------- log
    def log_mark(self, name):
        try:
            self.log_marks.append((name, os.path.getsize(self.log_file) if self.log_file else 0, r(self.now)))
        except Exception:  # noqa: BLE001
            pass

    def scan_log(self):
        if not self.log_file:
            return
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                txt = f.read()
            pats = {'airship': 'LogAirship', 'airship_warn': 'LogAirship: Warning', 'error': 'Error:', 'ensure': 'Ensure condition failed',
                    'accessed_none': 'Accessed None', 'rebuilt_body': 'rebuilt the physics body', 'user_play': 'Repeating last play command',
                    'corr_client': '*** Client: Error for', 'corr_server': '*** Server: Error for', 'giveability_client': 'on the client, not allowed',
                    'pilot': 'LogAirshipPilot', 'gun': 'HitActor', 'netdriver': 'LogNet: Warning', 'physrep': 'LogPhysics: Warning',
                    'hard_snap': 'Simulated HARD SNAP', 'hard_snap_lin': 'Hard snap due to linear difference error',
                    'hard_snap_acc': 'Hard snap due to accumulated error', 'repmode_guard': 'needs Project Settings > Physics > Physics Prediction'}
            sc = {}
            lines = txt.splitlines()
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                if k == 'error':
                    hit = [l for l in hit if 'not allowed' not in l and 'LoadErrors' not in l]
                sc[k] = {'count': len(hit), 'sample': hit[:10] + (hit[-5:] if len(hit) > 15 else [])}
            self.R['log_scan'] = sc
            seg = {}
            base = self.log_off
            marks = self.log_marks + [('eof', base + len(txt.encode('utf-8', 'replace')), r(self.now))]
            for i in range(len(marks) - 1):
                a = max(0, marks[i][1] - base)
                b = max(a, marks[i + 1][1] - base)
                chunk = txt.encode('utf-8', 'replace')[a:b].decode('utf-8', 'replace')
                seg[marks[i][0]] = {'corr_client': chunk.count('*** Client: Error for'), 'corr_server': chunk.count('*** Server: Error for'),
                                    'hard_snap_lin': chunk.count('Hard snap due to linear difference error'),
                                    'hard_snap_acc': chunk.count('Hard snap due to accumulated error'),
                                    'airship_warn': chunk.count('LogAirship: Warning'), 'error': len([l for l in chunk.splitlines() if 'Error:' in l and 'not allowed' not in l and 'LoadErrors' not in l])}
            self.R['log_segments'] = seg
            if sc['user_play']['count']:
                self.user_play = True
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    def scan_user_play(self):
        if not self.log_file or int(self.now * 2) == self.D.get('_ulast'):
            return
        self.D['_ulast'] = int(self.now * 2)
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                if 'Repeating last play command' in f.read():
                    self.user_play = True
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- PIE helpers
    def cmd(self, w, c):
        unreal.SystemLibrary.execute_console_command(w, c)
        self.event('cmd', cmd=c, world='server' if same(w, self.sw) else 'client')
        self.line('INFO', 'console (%s): %s' % ('server' if same(w, self.sw) else 'client', c))

    def subsystem(self, w):
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and same(lp.get_world(), w):
                    return s
            except Exception:  # noqa: BLE001
                pass
        return None

    def inject(self, which, action, x=1.0):
        sub = self.sub_c if which == 'client' else self.sub_s
        try:
            sub.inject_input_vector_for_action(self.act[action], unreal.Vector(x, 0.0, 0.0), [], [])
        except Exception:  # noqa: BLE001
            self.err('inject_' + action)

    def tele(self, ship):
        try:
            return parse_struct(ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def anim(self, ship):
        out = {}
        try:
            ai = ship.get_editor_property('Mesh').get_anim_instance()
        except Exception:  # noqa: BLE001
            return out
        if ai is None:
            return out
        for n in ANIM_VARS:
            try:
                v = ai.get_editor_property(n)
                out[n] = bool(v) if isinstance(v, bool) else round(float(v), 3)
            except Exception:  # noqa: BLE001
                out[n] = None
        return out

    def health(self, a):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None
            x = asc.get_gameplay_attribute_value(self.attrs['Health'])
            return round(float(x[0] if isinstance(x, tuple) else x), 2)
        except Exception:  # noqa: BLE001
            self.err('health')
            return None

    def mesh_rest(self, key, ship):
        m = ship.get_editor_property('Mesh')
        m.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES,
                              unreal.PropertyAccessChangeNotifyMode.NEVER)
        for b in BREAKOFF:
            try:
                self.rest[key][b] = v3(m.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_COMPONENT).translation)
            except Exception:  # noqa: BLE001
                self.err('mesh_rest')

    def breakoff(self, key, ship):
        out = {}
        try:
            m = ship.get_editor_property('Mesh')
            for b in BREAKOFF:
                if b in self.rest[key]:
                    out[b] = r(dist(v3(m.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_COMPONENT).translation), self.rest[key][b]), 1)
        except Exception:  # noqa: BLE001
            self.err('breakoff')
        return out

    def ship_state(self, ship, full=True):
        if not valid(ship):
            return None
        tr = ship.get_actor_transform()
        s = {'loc': r(v3(tr.translation), 1), 'q': [round(x, 6) for x in q4(tr.rotation)], 'vel': r(v3(ship.get_velocity()), 1),
             'role': en(ship.get_local_role())}
        t = self.tele(ship)
        for k in TELE_KEYS:
            if k in t:
                s[k] = r(t[k], 3) if isinstance(t[k], float) else t[k]
        if full:
            s['anim'] = self.anim(ship)
        return s

    def char_info(self, c, ship):
        if not valid(c):
            return None
        cm = gp(c, 'character_movement', 'CharacterMovement')
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        cl = v3(c.get_actor_location())
        base = c.get_movement_base() if hasattr(c, 'get_movement_base') else None
        par = c.get_attach_parent_actor()
        d = {'loc': r(cl, 1), 'mode': en(cm.get_editor_property('movement_mode')) if cm else None,
             'base': base.get_owner().get_name() if base is not None and base.get_owner() else (base.get_name() if base else None),
             'coll': en(caps.get_collision_enabled()) if caps else None, 'actor_coll': bool(c.get_actor_enable_collision()),
             'att': par.get_name() if par else None, 'role': en(c.get_local_role())}
        if valid(ship):
            x = unreal.MathLibrary.inverse_transform_location(ship.get_actor_transform(), unreal.Vector(*cl))
            d['local'] = r([x.x, x.y, x.z], 1)
            try:
                d['rider'] = c.get_name() in [p.get_name() for p in ship.get_passengers()]
            except Exception:  # noqa: BLE001
                d['rider'] = None
        return d

    def capsule_body(self, c):
        caps = gp(c, 'capsule_component', 'CapsuleComponent')
        if caps is None:
            return None
        p = c.get_actor_location()
        hh = caps.get_scaled_capsule_half_height()
        res = caps.line_trace_component(unreal.Vector(p.x, p.y, p.z + hh + 50.0), unreal.Vector(p.x, p.y, p.z - hh - 50.0), False, False, False)
        return bool(res[0] if isinstance(res, tuple) else res)

    def hud(self, pc, ship):
        d = {'shown': None, 'ship_widgets': [], 'overlay': []}
        try:
            d['shown'] = bool(ship.is_ship_hud_shown()) if valid(ship) else None
        except Exception:  # noqa: BLE001
            self.err('hud_shown')
        try:
            for uw in unreal.ObjectIterator(unreal.UserWidget):
                try:
                    if not uw.is_in_viewport():
                        continue
                    if not same(uw.get_owning_player(), pc):
                        continue
                    cn = uw.get_class().get_name()
                    if 'AirshipHUD' in cn:
                        d['ship_widgets'].append(en(uw.get_visibility()))
                    elif 'Overlay' in cn:
                        d['overlay'].append(en(uw.get_visibility()))
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            self.err('hud_iter')
        return d

    def hud_ok(self, h, flying):
        if flying:
            return h['shown'] is True and len(h['ship_widgets']) == 1 and bool(h['overlay']) and all(o == 'COLLAPSED' for o in h['overlay'])
        return not h['shown'] and not h['ship_widgets'] and bool(h['overlay']) and all(o != 'COLLAPSED' for o in h['overlay'])

    def deck_point(self, ship, side_y, char):
        seat = v3(ship.get_pilot_seat_location())
        rgt = v3(ship.get_actor_right_vector())
        up = v3(ship.get_actor_up_vector())
        p = [seat[i] + rgt[i] * side_y for i in range(3)]
        hull = ship.get_editor_property('HullCollision')
        hit = trace_loc(hull.line_trace_component(unreal.Vector(*[p[i] + up[i] * 400.0 for i in range(3)]),
                                                  unreal.Vector(*[p[i] - up[i] * 600.0 for i in range(3)]), False, False, False))
        caps = gp(char, 'capsule_component', 'CapsuleComponent')
        hh = caps.get_scaled_capsule_half_height() if caps else 90.0
        top = hit if hit is not None else [p[0], p[1], p[2] + 220.0]
        return [top[0], top[1], top[2] + hh + 40.0], hit is not None

    def tp(self, chars, loc, yaw):
        for c in chars:
            if not valid(c):
                continue
            try:
                c.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
                cm = gp(c, 'character_movement', 'CharacterMovement')
                if cm:
                    cm.stop_movement_immediately()
            except Exception:  # noqa: BLE001
                self.err('tp')

    def muzzle_comps(self, ship):
        out = []
        try:
            fx = ship.get_editor_property('MuzzleFX')
            m = ship.get_editor_property('Mesh')
            for c in m.get_children_components(True):
                if isinstance(c, unreal.NiagaraComponent) and fx is not None and same(c.get_asset(), fx):
                    out.append(c.get_name())
        except Exception:  # noqa: BLE001
            self.err('muzzle')
        return out

    def fx_state(self, ship):
        out = {}
        if not valid(ship):
            return out
        for c in ('ThrusterFX_FL', 'ThrusterFX_RR', 'TurbineFX_L', 'TurbineFX_R'):
            try:
                out[c] = bool(ship.get_editor_property(c).is_active())
            except Exception:  # noqa: BLE001
                self.err('fx_state')
        return out

    def track_balls(self):
        # Run 1 froze a ball at its first sighting when its bHidden read true there (the port volley: both balls then
        # flew 0.9 s to the wall and went 1 s after the impact, like the starboard ones). The impact is now where the
        # ball STOPS moving (Explode stops it and keeps it hidden for ImpactDestroyDelay); bHidden is only recorded.
        cls = unreal.load_class(None, BALL_CLS)
        for key, w in (('server', self.sw), ('client', self.cw)):
            try:
                seen = set()
                for b in unreal.GameplayStatics.get_all_actors_of_class(w, cls):
                    k = b.get_name()
                    seen.add(k)
                    p = v3(b.get_actor_location())
                    rec = self.balls[key].get(k)
                    if rec is None:
                        rec = {'first': r(p, 1), 't0': r(self.now), 'phase': self.phase, 'side': self.D.get('side')}
                        self.balls[key][k] = rec
                    if bool(gp(b, 'hidden', 'bHidden', default=False)):
                        rec.setdefault('t_hidden', r(self.now))
                        rec.setdefault('hidden_at', r(p, 1))
                    if rec.get('stopped'):
                        continue
                    if rec.get('last') is not None and dist(p, rec['last']) < 2.0 and self.now > rec['t_last']:
                        rec['stopped'] = True
                        rec['t_hit'] = rec['t_last']
                    else:
                        rec['last'] = r(p, 1)
                        rec['t_last'] = r(self.now)
                for k, rec in self.balls[key].items():
                    if k not in seen and not rec.get('gone'):
                        rec['gone'] = r(self.now)
            except Exception:  # noqa: BLE001
                self.err('balls')

    # ---------------------------------------------------------------- captures / X grabs
    def capture(self, w, label, kind, ship=None):
        key = 'server' if same(w, self.sw) else 'client'
        if self.cap_dead.get(key) or self.ncap >= MAX_CAPS:
            return None
        try:
            if key not in self.capres:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.SceneCapture2D) if TEMP in a.get_actor_label()]
                if not caps:
                    self.cap_dead[key] = True
                    self.line('WARN', 'no %s in the %s world: no captures there' % (TEMP, key))
                    return None
                rt = unreal.RenderingLibrary.create_render_target2d(w, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = caps[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('capture_every_frame', False)
                cc.set_editor_property('capture_on_movement', False)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.capres[key] = (caps[0], cc, rt)
            a, cc, rt = self.capres[key]
            fov = 60.0
            if kind == 'player':
                cm = unreal.GameplayStatics.get_player_camera_manager(w, 0)
                frm, rot, fov = cm.get_camera_location(), cm.get_camera_rotation(), cm.get_fov_angle()
            else:
                loc = v3(ship.get_actor_location())
                fwd = v3(ship.get_actor_forward_vector())
                rgt = v3(ship.get_actor_right_vector())

                def at(f, rr, u):
                    return [loc[i] + fwd[i] * f + rgt[i] * rr + (u if i == 2 else 0.0) for i in range(3)]
                if kind == 'side':
                    a0, a1 = at(2500, -5200, 1400), at(-300, 0, 0)
                elif kind == 'port':
                    a0, a1 = at(-4200, 2200, 2600), at(-300, -2600, 200)
                elif kind == 'stbd':
                    a0, a1 = at(-4200, -2200, 2600), at(-300, 2600, 200)
                elif kind == 'deck':
                    a0, a1 = at(-2200, -2600, 1500), at(-650, 0, 400)
                elif kind == 'wreck':
                    a0, a1 = at(3500, -6000, 3500), at(0, 0, -400)
                else:
                    return None
                frm = unreal.Vector(*a0)
                rot = unreal.MathLibrary.find_look_at_rotation(frm, unreal.Vector(*a1))
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(frm, rot, False, True)
            cc.capture_scene()
            name = '%s_%s_%s' % (label, kind, key)
            unreal.RenderingLibrary.export_render_target(w, rt, CAPS, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 'world': key, 't': r(self.now), 'file': os.path.join(CAPS, name + '.png')})
            self.line('INFO', 'capture %s' % name)
            return name
        except Exception:  # noqa: BLE001
            self.err('capture_' + key)
            self.cap_dead[key] = True
            return None

    def xgrab(self, label, which):
        try:
            with open(os.path.join(XG, label + '.req'), 'w') as f:
                f.write(which + '\n')
            self.R['xgrabs'].append({'label': label, 'which': which, 't': r(self.now), 'phase': self.phase})
        except Exception:  # noqa: BLE001
            self.err('xgrab')

    # ---------------------------------------------------------------- sampling
    def sample(self, force=False):
        per_frame = self.phase in PER_FRAME
        if not force and not per_frame and self.now - self.last_sample < 0.1:
            return None
        self.last_sample = self.now
        try:
            s = {'t': r(self.now, 3), 'ph': self.phase, 'el': r(self.now - self.p_t0, 3),
                 'tc': r(unreal.GameplayStatics.get_time_seconds(self.cw), 3) if self.cw else None}
            if per_frame:
                try:
                    s['cam'] = r(v3(unreal.GameplayStatics.get_player_camera_manager(self.cw, 0).get_camera_location()), 2)
                except Exception:  # noqa: BLE001
                    self.err('cam')
            two = self.phase in ('deck2', 'host_board', 'host_fly')
            if not two:
                s['S'] = self.ship_state(self.ship_s)
                s['C'] = self.ship_state(self.ship_c)
                s['cs'] = self.char_info(self.cchar_s, self.ship_s)
                s['cc'] = self.char_info(self.cchar_c, self.ship_c)
            else:
                s['S'] = self.ship_state(self.ship2_s)
                s['C'] = self.ship_state(self.ship2_c)
                s['cs'] = self.char_info(self.cchar_s, self.ship2_s)
                s['cc'] = self.char_info(self.cchar_c, self.ship2_c)
                s['hs'] = self.char_info(self.hchar, self.ship2_s)
                s['hc'] = self.char_info(self.hchar_c, self.ship2_c)
            self.R['series'].append(s)
            return s
        except Exception:  # noqa: BLE001
            self.err('sample')
            return None

    def ser(self, ph):
        return [s for s in self.R['series'] if s.get('ph') == ph]

    # ---------------------------------------------------------------- state machine
    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if sum(e['n'] for e in self.R['errors'].values()) > 300:
                self.finish('too many script errors')
        self.write()

    def role(self, w):
        try:
            if unreal.SystemLibrary.is_standalone(w):
                return 'standalone'
            return 'server' if unreal.SystemLibrary.is_server(w) else 'client'
        except Exception:  # noqa: BLE001
            return '?'

    def _tick(self):
        if self.phase == 'finished':
            return
        if self.phase == 'ending':
            self.end_tick()
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'wait_pie':
            ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
            sv = [w for w in ws if self.role(w) == 'server' and MAP_NAME in w.get_path_name()]
            cl = [w for w in ws if self.role(w) == 'client' and MAP_NAME in w.get_path_name()]
            if sv and cl:
                self.sw, self.cw = sv[0], cl[0]
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE worlds: server %s, client %s' % (self.sw.get_path_name(), self.cw.get_path_name()))
            elif time.time() - self.wall0 > 240:
                self.finish('listen PIE did not start in 240 s (worlds %s)' % [(w.get_path_name(), self.role(w)) for w in ws])
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        tw = unreal.GameplayStatics.get_time_seconds(self.sw)
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
        self.sample()
        if self.phase in ('cannons', 'gun', 'keys'):
            self.track_balls()
        el = self.now - self.p_t0
        ph = self.phase
        try:
            getattr(self, 'ph_' + ph, lambda e: None)(el)
        except Exception:  # noqa: BLE001
            self.err('ph_' + ph)
        if el >= PHASES[self.pi][1]:
            try:
                getattr(self, 'end_' + ph, lambda: None)()
            except Exception:  # noqa: BLE001
                self.err('end_' + ph)
                self.check(ph, 'FAIL', 'evaluation crashed: %s' % traceback.format_exc().strip().splitlines()[-1])
            self.write(True)
            self.next_phase()

    def next_phase(self):
        self.pi += 1
        if self.pi >= len(PHASES):
            self.finish('all phases done')
            return
        self.phase = PHASES[self.pi][0]
        self.p_t0 = self.now
        self.D = {}
        self.log_mark(self.phase)
        self.line('INFO', 'phase %s (%.0f s)' % (self.phase, PHASES[self.pi][1]))
        try:
            getattr(self, 'start_' + self.phase, lambda: None)()
        except Exception:  # noqa: BLE001
            self.err('start_' + self.phase)

    def find_actors(self):
        try:
            ship_cls = unreal.load_class(None, SHIP_CLS)
            self.hpc = unreal.GameplayStatics.get_player_controller(self.sw, 0)
            rem = [pc for pc in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.PlayerController) if not pc.is_local_controller()]
            self.rpc = rem[0] if rem else None
            self.cpc = unreal.GameplayStatics.get_player_controller(self.cw, 0)
            self.hchar = self.hpc.get_controlled_pawn() if self.hpc else None
            self.cchar_s = self.rpc.get_controlled_pawn() if self.rpc else None
            self.cchar_c = self.cpc.get_controlled_pawn() if self.cpc else None
            ss = unreal.GameplayStatics.get_all_actors_of_class(self.sw, ship_cls)
            cs = unreal.GameplayStatics.get_all_actors_of_class(self.cw, ship_cls)
            self.ship_s = ss[0] if ss else None
            self.ship_c = next((s for s in cs if self.ship_s and s.get_name() == self.ship_s.get_name()), None)
            if self.cchar_c:
                oth = [c for c in unreal.GameplayStatics.get_all_actors_of_class(self.cw, unreal.Character) if not same(c, self.cchar_c)]
                self.hchar_c = oth[0] if oth else None
            self.sub_s = self.subsystem(self.sw)
            self.sub_c = self.subsystem(self.cw)
            self.R['setup_try'] = {'hpc': bool(self.hpc), 'rpc': bool(self.rpc), 'cpc': bool(self.cpc), 'hchar': bool(self.hchar),
                                   'cchar_s': bool(self.cchar_s), 'cchar_c': bool(self.cchar_c), 'hchar_c': bool(self.hchar_c),
                                   'ship_s': bool(self.ship_s), 'ship_c': bool(self.ship_c), 'sub_s': bool(self.sub_s), 'sub_c': bool(self.sub_c)}
            if self.now > 3.0 and self.rpc and not self.cchar_s and 'restarted' not in self.R:
                gm = unreal.GameplayStatics.get_game_mode(self.sw)
                loc = self.hchar.get_actor_location() + unreal.Vector(0, 400, 300)
                gm.restart_player_at_transform(self.rpc, unreal.Transform(location=loc, rotation=unreal.Rotator(0, 0, 0)))
                self.R['restarted'] = str(loc)
                self.line('INFO', 'the client had no pawn: restart_player_at_transform next to the host')
            if all(self.R['setup_try'].values()):
                self.R['setup'] = {'server_world': self.sw.get_path_name(), 'client_world': self.cw.get_path_name(),
                                   'host_char': self.hchar.get_name(), 'client_char_server': self.cchar_s.get_name(),
                                   'client_char_client': self.cchar_c.get_name(), 'host_char_client': self.hchar_c.get_name(),
                                   'ship': self.ship_s.get_name(), 'ship_roles': (en(self.ship_s.get_local_role()), en(self.ship_c.get_local_role())),
                                   'client_char_loc': r(v3(self.cchar_s.get_actor_location()), 0), 'host_char_loc': r(v3(self.hchar.get_actor_location()), 0)}
                self.line('INFO', 'setup %s' % self.R['setup'])
                return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
        return False

    # ================================================================ phases
    # ---- settle: fps, corrections log on, the client hurt by 25 (restored-at-exit != refilled)
    def set_scheme(self, ship, which):
        """AS45_SCHEME on a server ship (it replicates to the client). Ship 1 in the settle phase, ship 2 the moment
        Aura.Airship.Spawn has made it (follow-up F-E: it started in the pawn's default, Point & Fly, so a Classic run's
        e3_hud_host_flying saw Point & Fly's two HUD widgets). The console fallback switches every ship of the world."""
        want = int(globals().get('AS45_SCHEME', 0) or 0)
        names = {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}
        try:
            ship.set_control_scheme(getattr(unreal.AirshipControlScheme, names[want]))
            self.line('INFO', 'control scheme set to %s on the server %s (AS45_SCHEME %d)' % (names[want], which, want))
        except Exception:  # noqa: BLE001
            self.err('set_control_scheme')
            self.cmd(self.sw, 'Aura.Airship.Scheme %d' % want)
        return names.get(want)

    def start_settle(self):
        self.cmd(self.sw, 'p.NetShowCorrections 1')
        # The v1 multiplayer checks run on Classic (AS45_SCHEME, default 0): since the 2026-11-23 polish the pawn's
        # default scheme is Point & Fly. Set on the server's ship (it replicates to the client before boarding).
        self.R.setdefault('setup', {})['scheme'] = self.set_scheme(self.ship_s, 'ship')
        self.D['wall0'] = time.time()
        self.D['f0'] = self.frames
        self.mesh_rest('server', self.ship_s)
        self.mesh_rest('client', self.ship_c)

    def ph_settle(self, el):
        if el >= 1.0 and 'hurt' not in self.D:
            self.D['hurt'] = True
            try:
                ge = unreal.load_class(None, DMG_GE)
                tag = unreal.GameplayTag()
                tag.import_text('(TagName="SetDamageByCaller")')
                asc = unreal.AbilitySystemLibrary.get_ability_system_component(self.cchar_s)
                spec = asc.make_outgoing_spec(ge, 1.0, asc.make_effect_context())
                spec = unreal.AbilitySystemLibrary.assign_tag_set_by_caller_magnitude(spec, tag, 25.0)
                asc.apply_gameplay_effect_spec_to_self(spec)
                self.line('INFO', 'client character hurt by 25 on the server (AirshipDamageEffect)')
            except Exception:  # noqa: BLE001
                self.err('hurt')

    def end_settle(self):
        fps = (self.frames - self.D['f0']) / max(0.01, time.time() - self.D['wall0'])
        self.R['mp']['real_fps_settle'] = r(fps, 2)
        self.R['mp']['pre_board_health'] = {'server': self.health(self.cchar_s), 'client': self.health(self.cchar_c)}
        self.line('INFO', 'real fps %.2f; client character health server %s / client %s' % (fps, self.R['mp']['pre_board_health']['server'],
                                                                                             self.R['mp']['pre_board_health']['client']))
        self.capture(self.sw, 'start', 'side', self.ship_s)

    # ---- F out of range: refused
    def start_board_far(self):
        self.D['d_seat'] = dist(v3(self.cchar_s.get_actor_location()), v3(self.ship_s.get_pilot_seat_location())) / 100.0

    def ph_board_far(self, el):
        if el >= 0.2 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client, out of range)')

    def end_board_far(self):
        ok = not self.ship_s.has_pilot() and same(self.cpc.get_controlled_pawn(), self.cchar_c)
        self.check('a0_board_out_of_range', 'PASS' if ok else 'FAIL', 'client F at %.1f m from the pilot seat (BoardDistance 12 m, '
                   'hull 4 m): ship has no pilot %s, client still on foot %s' % (self.D['d_seat'], not self.ship_s.has_pilot(),
                                                                                 same(self.cpc.get_controlled_pawn(), self.cchar_c)))

    # ---- teleport the client onto the deck (both copies)
    def start_board_tp(self):
        loc, traced = self.deck_point(self.ship_s, -250.0, self.cchar_s)
        self.D['tp'] = r(loc, 1)
        self.tp([self.cchar_s, self.cchar_c], loc, self.ship_s.get_actor_rotation().yaw)
        self.line('INFO', 'client character teleported onto the deck at %s (lid trace %s), server + client copies' % (r(loc, 0), traced))

    def end_board_tp(self):
        cs = self.char_info(self.cchar_s, self.ship_s)
        cc = self.char_info(self.cchar_c, self.ship_c)
        ok = all(x and x['mode'] == 'MOVE_WALKING' and x['coll'] == 'QUERY_ONLY' and x.get('rider') for x in (cs, cc))
        self.check('a0b_on_deck', 'PASS' if ok else 'FAIL', 'client character on the deck before boarding: server copy %s; client copy %s'
                   % (cs, cc), {'server': cs, 'client': cc})
        self.D['pre'] = {'server': cs, 'client': cc}

    # ---- (a) the client boards with F (its own RPC)
    def ph_board(self, el):
        if el >= 0.2 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('client', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (client)')
        if 'srv_t' not in self.D and self.ship_s.has_pilot():
            self.D['srv_t'] = r(el, 3)
        if 'cli_t' not in self.D and same(self.cpc.get_controlled_pawn(), self.ship_c):
            self.D['cli_t'] = r(el, 3)
        if el >= 1.2 and 'fb' not in self.D and not self.ship_s.has_pilot():
            self.D['fb'] = True
            self.cpc.get_component_by_class(unreal.load_class(None, '/Script/Aura.AirshipPilotComponent')).request_board()
            self.line('WARN', 'F injection did not board in 1 s: fallback UAirshipPilotComponent.RequestBoard on the client')
        if el >= 2.0 and 'hud' not in self.D:
            self.D['hud'] = True
            self.D['hud_c'] = self.hud(self.cpc, self.ship_c)
            self.D['hud_h'] = self.hud(self.hpc, self.ship_s)
            self.xgrab('board', 'both')
            self.capture(self.cw, 'board', 'player')
            self.capture(self.sw, 'board', 'side', self.ship_s)

    def end_board(self):
        srv = {'pilot': self.ship_s.get_pilot().get_name() if self.ship_s.get_pilot() else None,
               'controller': self.ship_s.get_controller().get_name() if self.ship_s.get_controller() else None,
               'pilot_is_client': same(self.ship_s.get_pilot(), self.cchar_s), 'ctrl_is_remote_pc': same(self.ship_s.get_controller(), self.rpc),
               'char_att': self.cchar_s.get_attach_parent_actor().get_name() if self.cchar_s.get_attach_parent_actor() else None}
        cli = {'possessed': same(self.cpc.get_controlled_pawn(), self.ship_c), 'has_pilot': bool(self.ship_c.has_pilot()),
               'role': en(self.ship_c.get_local_role()), 'char_att': self.cchar_c.get_attach_parent_actor().get_name() if self.cchar_c.get_attach_parent_actor() else None,
               'char_actor_coll': bool(self.cchar_c.get_actor_enable_collision())}
        ok = (srv['pilot_is_client'] and srv['ctrl_is_remote_pc'] and srv['char_att'] == self.ship_s.get_name() and cli['possessed']
              and cli['has_pilot'] and cli['role'] == 'ROLE_AUTONOMOUS_PROXY' and cli['char_att'] == self.ship_c.get_name()
              and not cli['char_actor_coll'] and not self.D.get('fb'))
        self.check('a1_client_board', 'PASS' if ok else 'FAIL', 'client F (IA_AirshipBoard -> UAirshipPilotComponent::ServerRequestBoard)%s: '
                   'server: %s, boarded %.2f s after F; client: %s, possessed %.2f s after F'
                   % (' (FALLBACK RequestBoard used)' if self.D.get('fb') else '', srv, (self.D.get('srv_t') or -1) - 0.2, cli,
                      (self.D.get('cli_t') or -1) - 0.2), {'server': srv, 'client': cli})
        hc, hh = self.D.get('hud_c') or {}, self.D.get('hud_h') or {}
        ok2 = bool(hc) and self.hud_ok(hc, True) and bool(hh) and self.hud_ok(hh, False)
        self.check('b1_hud_board', 'PASS' if ok2 else 'FAIL', 'client (pilot) HUD: %s (want ship HUD shown, 1 widget, its overlay COLLAPSED); '
                   'host (on foot) HUD: %s (want no ship HUD, overlay visible)' % (hc, hh), {'client': hc, 'host': hh})

    # ---- hover: baseline server/client error
    def start_hover(self):
        self.ship_c.debug_clear_input()
        self.D['wall0'] = time.time()
        self.D['f0'] = self.frames

    def end_hover(self):
        fps = (self.frames - self.D['f0']) / max(0.01, time.time() - self.D['wall0'])
        self.R['mp']['real_fps_hover'] = r(fps, 2)
        e = self.errors('hover')
        self.R['mp']['err_hover'] = e
        ok = e is not None and e['pos']['max'] < 100.0
        self.check('a2_hover_sync', 'PASS' if ok else 'FAIL', 'client pilot, neutral 4 s: server vs client ship position error %s cm, '
                   'rotation error %s deg; real fps %.1f' % (e and e['pos'], e and e['rot'], fps), e)

    # ---- (c) cannons fired by the client
    def look(self, side):
        y = self.ship_c.get_actor_rotation().yaw + (-90.0 if side == 'port' else 90.0)
        self.cpc.set_control_rotation(unreal.Rotator(0.0, -4.0, y))

    def start_cannons(self):
        self.D['side'] = 'port'
        self.D['mz'] = {'server': {}, 'client': {}}
        self.D['recoil'] = {'server': {}, 'client': {}}
        self.D['n_srv0'] = len(self.balls['server'])

    def fire(self, side):
        self.D['side'] = side
        self.D['fire_t_' + side] = self.now
        # muzzle FX components already there (an earlier volley's may still be alive): only new ones count
        self.D['mz_old_' + side] = {'server': set(self.muzzle_comps(self.ship_s)), 'client': set(self.muzzle_comps(self.ship_c))}
        self.D['vel0_' + side] = {'server': v3(self.ship_s.get_velocity()), 'client': v3(self.ship_c.get_velocity())}
        self.D['nb0_' + side] = len(self.balls['server'])
        self.inject('client', 'IA_AirshipFire')
        self.event('inject', what='IA_AirshipFire (client, %s)' % side)
        self.line('INFO', 'client fire (%s) injected' % side)

    def ph_cannons(self, el):
        if el < 1.6:
            self.look('port')
        if el >= 1.6 and 'fire_t_port' not in self.D:
            self.fire('port')
        if 3.6 < el < 5.2:
            self.look('stbd')
        if el >= 5.2 and 'fire_t_stbd' not in self.D:
            self.fire('stbd')
        for side in ('port', 'stbd'):
            ft = self.D.get('fire_t_' + side)
            if ft is None:
                continue
            if self.now - ft >= 0.6 and 'fb_' + side not in self.D and len(self.balls['server']) == self.D['nb0_' + side]:
                self.D['fb_' + side] = True
                self.ship_c.request_fire()
                self.line('WARN', 'fire injection made no ball in 0.6 s: fallback RequestFire on the client ship (%s)' % side)
            if self.now - ft <= 1.6:
                for key, ship in (('server', self.ship_s), ('client', self.ship_c)):
                    for c in self.muzzle_comps(ship):
                        if c not in self.D['mz_old_' + side][key]:
                            self.D['mz'][key].setdefault(side, set()).add(c)
                    av = self.anim(ship)
                    for c in (('L1', 'L2') if side == 'port' else ('R1', 'R2')):
                        k = 'CannonRecoilCm_' + c
                        rec = self.D['recoil'][key].setdefault(c, {'max': 0.0, 't_max': None, 'peaks': 0, 'prev': 0.0, 'rising': False})
                        v = av.get(k) or 0.0
                        if v > rec['max']:
                            rec['max'] = round(v, 2)
                            rec['t_max'] = round(self.now - ft, 3)
                        if v > rec['prev'] + 0.05 and not rec['rising']:
                            rec['rising'] = True
                            rec['peaks'] += 1
                        elif v < rec['prev'] - 0.05:
                            rec['rising'] = False
                        rec['prev'] = v
                    if 0.2 <= self.now - ft and 'kick_' + side + key not in self.D:
                        self.D['kick_' + side + key] = r(dist(v3(ship.get_velocity()), self.D['vel0_' + side][key]), 1)
                if self.now - ft >= 0.12 and 'cap_' + side not in self.D:
                    self.D['cap_' + side] = True
                    self.capture(self.sw, 'cannons_' + side, side, self.ship_s)
                    self.capture(self.cw, 'cannons_' + side, side, self.ship_c)

    def end_cannons(self):
        self.track_balls()
        msgs, ok = [], True
        res = {}
        for side, wall_y in (('port', -9500.0 + 200.0), ('stbd', 14500.0 - 200.0)):
            bs = [b for b in self.balls['server'].values() if b.get('side') == side and b.get('phase') == 'cannons']
            bc = [b for b in self.balls['client'].values() if b.get('side') == side and b.get('phase') == 'cannons']
            # impact = where the ball went hidden (Explode / MulticastImpact), else where it stopped (run 3: the first
            # volley of an as_45 run did not advance for one frame right after spawn, on both machines, then flew on)
            hits_s = [b for b in bs if (b.get('hidden_at') or b.get('last')) and abs((b.get('hidden_at') or b['last'])[1] - wall_y) < 600.0]
            hits_c = [b for b in bc if (b.get('hidden_at') or b.get('last')) and abs((b.get('hidden_at') or b['last'])[1] - wall_y) < 600.0]
            mz_s = len(self.D['mz']['server'].get(side, ()))
            mz_c = len(self.D['mz']['client'].get(side, ()))
            cs = ('L1', 'L2') if side == 'port' else ('R1', 'R2')
            rec_s = dict((c, self.D['recoil']['server'].get(c, {}).get('max')) for c in cs)
            rec_c = dict((c, self.D['recoil']['client'].get(c, {}).get('max')) for c in cs)
            peaks_c = dict((c, self.D['recoil']['client'].get(c, {}).get('peaks')) for c in cs)
            kick = {'server': self.D.get('kick_' + side + 'server'), 'client': self.D.get('kick_' + side + 'client')}
            # muzzle FX count = shown once per cannon on each machine (the client's prediction + a multicast it failed to
            # skip would make 4); the recoil peak count is only reported (the curve's own shape could add a peak)
            sok = (len(bs) == 2 and len(bc) == 2 and len(hits_s) >= 1 and mz_s == 2 and mz_c == 2
                   and all((v or 0) > 5.0 for v in rec_s.values()) and all((v or 0) > 5.0 for v in rec_c.values())
                   and not self.D.get('fb_' + side))
            ok = ok and sok
            res[side] = {'server_balls': bs, 'client_balls': bc, 'muzzle_fx': {'server': mz_s, 'client': mz_c}, 'recoil_cm': {'server': rec_s, 'client': rec_c},
                         'client_recoil_peaks': peaks_c, 'hull_kick_cms': kick}
            msgs.append('%s: server balls %d (%d ended at the wall y %.0f, last %s), client balls %d (%d at the wall), muzzle FX server %d / '
                        'client %d, recoil anim max cm server %s client %s (client peaks per cannon %s: 1 = shown once), hull speed change '
                        'after 0.2 s cm/s %s%s' % (side, len(bs), len(hits_s), wall_y, [b.get('last') for b in bs], len(bc), len(hits_c), mz_s,
                                                   mz_c, rec_s, rec_c, peaks_c, kick, ' FALLBACK RequestFire' if self.D.get('fb_' + side) else ''))
        self.check('c_cannons', 'PASS' if ok else 'FAIL', '; '.join(msgs), res)

    # ---- (b) the host shoots the client's ship with GA_GunShoot
    def host_aim(self, target):
        cm = unreal.GameplayStatics.get_player_camera_manager(self.sw, 0)
        self.hpc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(cm.get_camera_location(), target))

    def start_gun(self):
        self.ship_c.debug_clear_input()
        self.D['h0'] = {'server': self.tele(self.ship_s).get('Health'), 'client': self.tele(self.ship_c).get('Health')}
        self.D['hs'] = []
        self.D['n'] = 0

    def ph_gun(self, el):
        tgt = self.ship_s.get_actor_location() + unreal.Vector(0.0, 0.0, 150.0)
        if el < 4.0:
            self.host_aim(tgt)
        if 1.0 <= el < 4.0:
            self.inject('server', 'IA_LMB')
            self.D['n'] += 1
        hs, hc = self.tele(self.ship_s).get('Health'), self.tele(self.ship_c).get('Health')
        if not self.D['hs'] or self.D['hs'][-1][1] != hs or self.D['hs'][-1][2] != hc:
            self.D['hs'].append((r(el, 3), hs, hc))
        if el >= 2.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.sw, 'gun_host_view', 'player')

    def end_gun(self):
        hs = [x for x in self.D['hs'] if x[1] is not None and x[2] is not None]
        h0s, h0c = self.D['h0']['server'], self.D['h0']['client']
        h1s, h1c = (hs[-1][1], hs[-1][2]) if hs else (None, None)
        drops = [hs[i][1] - hs[i + 1][1] for i in range(len(hs) - 1) if hs[i + 1][1] < hs[i][1]]
        lag = None
        ts = next((x[0] for x in hs if h0s is not None and x[1] < h0s), None)   # first server drop -> first client drop
        tc = next((x[0] for x in hs if h0c is not None and x[2] < h0c), None)
        if ts is not None and tc is not None:
            lag = r(tc - ts, 3)
        ok = h1s is not None and h1c is not None and h0s is not None and h1s < h0s and abs(h1s - h1c) < 0.5
        self.check('b2_host_gun', 'PASS' if ok else 'FAIL', 'host on foot fires GA_GunShoot (IA_LMB injected %d frames, aimed at the ship): '
                   'ship health server %s -> %s, client %s -> %s; %d hits on the server %s; client saw the first drop %s s after the '
                   'server' % (self.D['n'], h0s, h1s, h0c, h1c, len(drops), r(drops, 2), lag), {'health_track': hs})

    # ---- (a) real key path: throttle / steer injected on the client
    def ph_keys(self, el):
        if 0.3 <= el < 2.3:
            self.inject('client', 'IA_AirshipThrottle', 1.0)
        if 1.3 <= el < 2.3:
            self.inject('client', 'IA_AirshipSteer', 1.0)

    def end_keys(self):
        ss = self.ser('keys')
        thr_s = max((s['S'].get('Throttle') or 0) for s in ss if s.get('S'))
        thr_c = max((s['C'].get('Throttle') or 0) for s in ss if s.get('C'))
        st_s = max((s['S'].get('Steer') or 0) for s in ss if s.get('S'))
        st_c = max((s['C'].get('Steer') or 0) for s in ss if s.get('C'))
        v0 = ss[0]['S'].get('ForwardSpeedMS') or 0
        vmax = max((s['S'].get('ForwardSpeedMS') or 0) for s in ss if s.get('S'))
        ok = thr_s > 0.5 and thr_c > 0.5 and st_s > 0.3 and vmax > v0 + 0.5
        self.check('a3_keys_rpc', 'PASS' if ok else 'FAIL', 'IA_AirshipThrottle (2 s) + IA_AirshipSteer (1 s) injected into the CLIENT\'s '
                   'Enhanced Input: shaped throttle max client %.2f / server %.2f, steer max client %.2f / server %.2f, server forward '
                   'speed %.2f -> %.2f m/s' % (thr_c, thr_s, st_c, st_s, v0, vmax))

    # ---- (a) client flight via DebugSetInput on the CLIENT's ship, without / with lag
    def fly_tick(self, el):
        for t, name, inp in FLY:
            if el >= t and name not in self.D:
                self.D[name] = r(self.now, 3)
                self.ship_c.debug_set_input(*inp)
                self.event('client_input', edge=name, input=inp)
        self.host_aim(self.ship_s.get_actor_location())
        if 6.5 <= el and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.sw, self.phase + '_host_view', 'player')
            self.capture(self.cw, self.phase + '_client_view', 'player')

    def ph_fly0(self, el):
        self.fly_tick(el)

    def ph_fly1(self, el):
        self.fly_tick(el)

    def end_fly0(self):
        self.fly_eval('fly0')

    def end_fly1(self):
        self.fly_eval('fly1')

    def first(self, ss, t0, fn):
        for s in ss:
            if s['t'] >= t0 - 1e-6:
                try:
                    if fn(s):
                        return r(s['t'] - t0, 3)
                except Exception:  # noqa: BLE001
                    continue
        return None

    def fly_eval(self, ph):
        ss = [s for s in self.ser(ph) if s.get('S') and s.get('C')]
        lat = {}
        for t, name, inp in FLY:
            if not name.startswith('E'):
                continue
            t0 = self.D.get(name)
            if t0 is None:
                continue
            b = [s for s in ss if s['t'] <= t0]
            b = b[-1] if b else ss[0]
            if name == 'E1_throttle':
                L = {'client_controls': self.first(ss, t0, lambda s: s['C']['Throttle'] > b['C']['Throttle'] + 0.05),
                     'client_cosmetic_nozzle': self.first(ss, t0, lambda s: abs(s['C']['anim']['NozzlePitchDeg_FL'] - b['C']['anim']['NozzlePitchDeg_FL']) > 0.2),
                     'server_controls': self.first(ss, t0, lambda s: s['S']['Throttle'] > b['S']['Throttle'] + 0.05),
                     'host_cosmetic_nozzle': self.first(ss, t0, lambda s: abs(s['S']['anim']['NozzlePitchDeg_FL'] - b['S']['anim']['NozzlePitchDeg_FL']) > 0.2),
                     'server_physics': self.first(ss, t0, lambda s: s['S']['ForwardSpeedMS'] > b['S']['ForwardSpeedMS'] + 0.1),
                     'client_physics': self.first(ss, t0, lambda s: s['C']['ForwardSpeedMS'] > b['C']['ForwardSpeedMS'] + 0.1)}
            elif name in ('E2_steer_right', 'E3_steer_left'):
                sg = 1.0 if name == 'E2_steer_right' else -1.0
                L = {'client_controls': self.first(ss, t0, lambda s: sg * (s['C']['Steer'] - b['C']['Steer']) > 0.05),
                     'client_cosmetic_wheel': self.first(ss, t0, lambda s: abs(s['C']['anim']['WheelAngleDeg'] - b['C']['anim']['WheelAngleDeg']) > 2.0),
                     'client_cosmetic_fans': self.first(ss, t0, lambda s: abs(s['C']['anim']['TurbineYawDeg_L'] - b['C']['anim']['TurbineYawDeg_L']) > 0.5),
                     'server_controls': self.first(ss, t0, lambda s: sg * (s['S']['Steer'] - b['S']['Steer']) > 0.05),
                     'host_cosmetic_wheel': self.first(ss, t0, lambda s: abs(s['S']['anim']['WheelAngleDeg'] - b['S']['anim']['WheelAngleDeg']) > 2.0),
                     'server_physics': self.first(ss, t0, lambda s: sg * (s['S']['YawRateDegS'] - b['S']['YawRateDegS']) > 0.5),
                     'client_physics': self.first(ss, t0, lambda s: sg * (s['C']['YawRateDegS'] - b['C']['YawRateDegS']) > 0.5)}
            else:
                L = {'client_controls': self.first(ss, t0, lambda s: s['C']['bBraking'] is True),
                     'server_controls': self.first(ss, t0, lambda s: s['S']['bBraking'] is True),
                     'server_physics': self.first(ss, t0, lambda s: s['S']['ForwardSpeedMS'] < b['S']['ForwardSpeedMS'] - 0.3),
                     'client_physics': self.first(ss, t0, lambda s: s['C']['ForwardSpeedMS'] < b['C']['ForwardSpeedMS'] - 0.3)}
            lat[name] = L
        e = self.errors(ph)
        top = max((s['S'].get('ForwardSpeedMS') or 0) for s in ss) if ss else 0
        self.R['mp']['lat_' + ph] = lat
        self.R['mp']['err_' + ph] = e
        srv_ok = all(L.get('server_controls') is not None and L.get('server_physics') is not None for L in lat.values()) and len(lat) == 4
        cli_ok = all(L.get('client_controls') is not None and L.get('client_controls') <= 0.07 for L in lat.values())
        ok = srv_ok and cli_ok and top > 10.0 and e is not None
        self.check('a4_' + ph, 'PASS' if ok else 'FAIL', '%s (%s): DebugSetInput on the CLIENT ship -> server applied every edge %s, client '
                   'shaped controls at once %s; top speed %.1f m/s; response delays (s after the input) %s; server vs client ship: '
                   'position error %s cm, rotation error %s deg, best lag fit %s frames -> residual %s cm, client snaps %s, accel noise '
                   'client %s vs server %s cm/frame^2' % (ph, 'Net PktLag=%s on both worlds' % self.R['mp'].get('pktlag') if ph == 'fly1' else 'no lag',
                                                         srv_ok, cli_ok, top, lat, e and e['pos'], e and e['rot'], e and e['lag_frames'],
                                                         e and e['residual'], e and e['snaps'], e and e['acc_client'], e and e['acc_server']),
                   {'lat': lat, 'err': e})

    def errors(self, ph):
        ss = [s for s in self.ser(ph) if s.get('S') and s.get('C')]
        if len(ss) < 10:
            return None
        ps = [s['S']['loc'] for s in ss]
        pc = [s['C']['loc'] for s in ss]
        n = len(ss)
        pos = [dist(ps[i], pc[i]) for i in range(n)]
        rot = [qang(ss[i]['S']['q'], ss[i]['C']['q']) for i in range(n)]
        best = None
        # k > 0: the client shows where the server was k frames ago; k < 0: the client is ahead (it simulated a step
        # after applying the server's newest state)
        for k in range(-4, 16):
            d = [dist(pc[i], ps[i - k]) for i in range(max(0, k), min(n, n + k))]
            m = sum(d) / max(1, len(d))
            if best is None or m < best[1]:
                best = (k, m, d)

        def acc(p):
            return [dist([p[i + 1][j] - 2 * p[i][j] + p[i - 1][j] for j in range(3)], [0, 0, 0]) for i in range(1, len(p) - 1)]
        acc_c, acc_s = acc(pc), acc(ps)
        snaps = [r(ss[i]['t'], 2) for i in range(1, n - 1) if acc_c[i - 1] > 10.0]
        out = {'pos': stats(pos), 'rot': stats(rot), 'lag_frames': best[0], 'residual': stats(best[2]), 'acc_client': stats(acc_c),
               'acc_server': stats(acc_s), 'snaps': {'n_over_10cm_per_frame2': len(snaps), 'at': snaps[:12]}, 'frames': n}
        # what the client pilot sees: the ship relative to its own (lagged, smoothed) camera
        cam = [s.get('cam') for s in ss]
        if all(c is not None for c in cam):
            rel = [[pc[i][j] - cam[i][j] for j in range(3)] for i in range(n)]
            out['acc_view'] = stats(acc(rel))
        return out

    # ---- lag on / off (Net PktLag is real time: scaled by the real fps so the game-time lag is ~LAG_GAME_MS each way)
    def start_lag_on(self):
        self.ship_c.debug_set_input(*BRAKE)
        fps = self.R['mp'].get('real_fps_hover') or 30.0
        n = int(round(max(100.0, min(1000.0, LAG_GAME_MS * FIXED_FPS / max(1.0, fps)))))
        self.R['mp']['pktlag'] = n
        self.cmd(self.cw, 'Net PktLag=%d' % n)
        self.cmd(self.sw, 'Net PktLag=%d' % n)

    def end_lag_on(self):
        self.ship_c.debug_set_input(*NEUTRAL)

    def start_lag_off(self):
        self.ship_c.debug_set_input(*BRAKE)
        self.cmd(self.cw, 'Net PktLag=0')
        self.cmd(self.sw, 'Net PktLag=0')

    def end_lag_off(self):
        self.ship_c.debug_clear_input()

    # ---- the client leaves the helm with F (ServerRequestExit) and boards again
    def start_c_exit(self):
        self.ship_c.debug_clear_input()

    def ph_c_exit(self, el):
        if el >= 0.2 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('client', 'IA_AirshipExit')
            self.event('inject', what='IA_AirshipExit (client)')
        if 'srv_t' not in self.D and not self.ship_s.has_pilot():
            self.D['srv_t'] = r(el, 3)
        if 'cli_t' not in self.D and same(self.cpc.get_controlled_pawn(), self.cchar_c):
            self.D['cli_t'] = r(el, 3)
        if el >= 1.2 and 'fb' not in self.D and self.ship_s.has_pilot():
            self.D['fb'] = True
            self.cpc.get_component_by_class(unreal.load_class(None, '/Script/Aura.AirshipPilotComponent')).request_exit()
            self.line('WARN', 'exit injection did nothing in 1 s: fallback UAirshipPilotComponent.RequestExit on the client')
        if el >= 2.5 and 'hud' not in self.D:
            self.D['hud'] = True
            self.D['hud_c'] = self.hud(self.cpc, self.ship_c)
            self.capture(self.cw, 'exit', 'deck', self.ship_c)

    def end_c_exit(self):
        pb = self.R['mp'].get('pre_board_health') or {}
        hs, hc = self.health(self.cchar_s), self.health(self.cchar_c)
        ss = [s for s in self.ser('c_exit') if s['el'] >= 2.0 and s.get('cs') and s.get('cc')]
        out = {}
        for key, c in (('server', 'cs'), ('client', 'cc')):
            rel = [s[c]['local'][2] for s in ss if s[c].get('local')]
            out[key] = {'rel_z_span_cm': r(max(rel) - min(rel), 1) if rel else None, 'rel_z_m': r(sum(rel) / len(rel) / 100.0, 2) if rel else None,
                        'last': ss[-1][c] if ss else None}
        out['server']['body'] = self.capsule_body(self.cchar_s)
        out['client']['body'] = self.capsule_body(self.cchar_c)
        ok1 = (not self.ship_s.has_pilot() and same(self.rpc.get_controlled_pawn(), self.cchar_s) and same(self.cpc.get_controlled_pawn(), self.cchar_c)
               and self.cchar_s.get_attach_parent_actor() is None and self.cchar_c.get_attach_parent_actor() is None
               and hs is not None and abs(hs - (pb.get('server') or -1)) < 0.5 and abs((hc or -1) - (pb.get('client') or -2)) < 0.5 and not self.D.get('fb'))
        self.check('k1_client_exit', 'PASS' if ok1 else 'FAIL', 'client F (IA_AirshipExit -> AAirshipPawn::ServerRequestExit)%s: server unboarded '
                   '%.2f s after F, client re-possessed its character %.2f s after F; health server %s client %s (before boarding %s, want '
                   'equal: restored, not refilled); client HUD %s' % (' (FALLBACK RequestExit)' if self.D.get('fb') else '', (self.D.get('srv_t') or -1) - 0.2,
                                                                     (self.D.get('cli_t') or -1) - 0.2, hs, hc, pb, self.D.get('hud_c')),
                   {'hud': self.D.get('hud_c')})
        ok2 = all(out[k]['body'] is True and out[k]['last'] and out[k]['last']['coll'] == 'QUERY_ONLY' and out[k]['last']['mode'] == 'MOVE_WALKING'
                  and out[k]['last'].get('rider') and out[k]['rel_z_span_cm'] is not None and out[k]['rel_z_span_cm'] < 30.0 for k in ('server', 'client'))
        ok3 = bool(self.D.get('hud_c')) and self.hud_ok(self.D['hud_c'], False)
        self.check('k2_client_exit_body', 'PASS' if ok2 else 'FAIL', 'after the exit, both copies of the client character: %s' % out, out)
        self.check('b3_hud_exit', 'PASS' if ok3 else 'FAIL', 'client HUD after exit: %s (want no ship HUD, overlay visible)' % self.D.get('hud_c'))

    def ph_c_board2(self, el):
        if el >= 0.2 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('client', 'IA_AirshipBoard')
        if el >= 1.2 and 'fb' not in self.D and not self.ship_s.has_pilot():
            self.D['fb'] = True
            self.cpc.get_component_by_class(unreal.load_class(None, '/Script/Aura.AirshipPilotComponent')).request_board()
            self.line('WARN', 'F injection did not board in 1 s: fallback RequestBoard (board 2)')

    def end_c_board2(self):
        ok = same(self.ship_s.get_pilot(), self.cchar_s) and same(self.cpc.get_controlled_pawn(), self.ship_c) and not self.D.get('fb')
        self.check('a5_client_board_again', 'PASS' if ok else 'FAIL', 'client F from the deck: boarded again %s%s' % (ok, ' (fallback)' if self.D.get('fb') else ''))

    # ---- (d) Aura.Airship.Kill on the server
    def start_kill(self):
        self.ship_c.debug_clear_input()
        self.D['dead'] = {}
        self.D['fx'] = {}
        self.D['parts'] = {'server': {}, 'client': {}}
        self.D['char'] = []

    def ph_kill(self, el):
        if el >= 0.3 and 'killed' not in self.D:
            self.D['killed'] = r(self.now, 3)
            self.D['loc0'] = v3(self.ship_s.get_actor_location())
            self.cmd(self.sw, 'Aura.Airship.Kill')
        if 'killed' not in self.D:
            return
        for key, ship in (('server', self.ship_s), ('client', self.ship_c)):
            if not valid(ship):
                continue
            if key not in self.D['dead'] and ship.is_airship_dead():
                self.D['dead'][key] = r(self.now, 3)
            dt = self.D['dead'].get(key)
            if dt is not None:
                for at in (0.3, 3.0):
                    k = '%s_%.1f' % (key, at)
                    if self.now >= dt + at and k not in self.D['fx']:
                        self.D['fx'][k] = {'fx': self.fx_state(ship), 'anim': dict((n, self.anim(ship).get(n)) for n in ('bIsDead', 'DeathTime'))}
                if int(el * 5) != self.D.get('_p' + key):
                    self.D['_p' + key] = int(el * 5)
                    for b, d in self.breakoff(key, ship).items():
                        self.D['parts'][key][b] = max(self.D['parts'][key].get(b, 0.0), d)
        if int(el * 10) != self.D.get('_c'):
            self.D['_c'] = int(el * 10)
            self.D['char'].append({'t': r(el, 2), 'cs': self.char_info(self.cchar_s, None), 'cc': self.char_info(self.cchar_c, None),
                                   'srv_pawn_is_char': same(self.rpc.get_controlled_pawn(), self.cchar_s),
                                   'cli_pawn_is_char': same(self.cpc.get_controlled_pawn(), self.cchar_c)})
        if el >= 2.0 and 'hud' not in self.D:
            self.D['hud'] = True
            self.D['hud_c'] = self.hud(self.cpc, self.ship_c)
            self.D['health'] = {'server': self.health(self.cchar_s), 'client': self.health(self.cchar_c)}
            self.D['body'] = {'server': self.capsule_body(self.cchar_s), 'client': self.capsule_body(self.cchar_c)}
            self.xgrab('after_death', 'client')
            self.capture(self.sw, 'kill', 'wreck', self.ship_s)
            self.capture(self.cw, 'kill', 'wreck', self.ship_c)
        if el >= 6.0 and 'cap2' not in self.D:
            self.D['cap2'] = True
            self.capture(self.cw, 'kill_late', 'wreck', self.ship_c)

    def end_kill(self):
        dead = self.D['dead']
        fx = self.D['fx']
        fx_ok = all(('%s_0.3' % k) in fx and not fx['%s_0.3' % k]['fx'].get('ThrusterFX_FL') and not fx['%s_0.3' % k]['fx'].get('ThrusterFX_RR')
                    and ('%s_3.0' % k) in fx and not fx['%s_3.0' % k]['fx'].get('TurbineFX_L') and not fx['%s_3.0' % k]['fx'].get('TurbineFX_R')
                    and fx['%s_0.3' % k]['anim'].get('bIsDead') is True for k in ('server', 'client'))
        parts = self.D['parts']
        parts_ok = all(parts[k] and max(parts[k].values()) > 100.0 for k in ('server', 'client'))
        ok1 = 'server' in dead and 'client' in dead and fx_ok and parts_ok
        self.check('d1_death_both', 'PASS' if ok1 else 'FAIL', 'Aura.Airship.Kill (server) at %s: dead on the server at %s, on the client at %s '
                   '(%s s later); FX / rig 0.3 s and 3 s after each machine\'s death %s; break-off parts max distance from their rest (cm) %s'
                   % (self.D.get('killed'), dead.get('server'), dead.get('client'),
                      r((dead.get('client') or 0) - (dead.get('server') or 0), 3) if dead.get('client') and dead.get('server') else None, fx, parts),
                   {'fx': fx, 'parts': parts, 'dead': dead})
        ch = self.D['char']
        last = ch[-1] if ch else {}
        ej = next((c for c in ch if c['srv_pawn_is_char']), None)
        ejc = next((c for c in ch if c['cli_pawn_is_char']), None)
        pb = self.R['mp'].get('pre_board_health') or {}
        hl = self.D.get('health') or {}
        body = self.D.get('body') or {}
        cs, cc = last.get('cs') or {}, last.get('cc') or {}
        land_ok = cs.get('mode') == 'MOVE_WALKING' and cc.get('mode') == 'MOVE_WALKING' and cs.get('loc') and cc.get('loc') and dist(cs['loc'], cc['loc']) < 100.0
        ok2 = (ej is not None and ejc is not None and cs.get('att') is None and cc.get('att') is None and body.get('server') is True and body.get('client') is True
               and hl.get('server') is not None and abs(hl['server'] - (pb.get('server') or -1)) < 0.5 and abs((hl.get('client') or -1) - (pb.get('client') or -2)) < 0.5
               and land_ok)
        self.check('d2_pilot_ejected', 'PASS' if ok2 else 'FAIL', 'pilot ejected: server re-possessed at %s s, client at %s s (phase time); '
                   'health 2 s after: server %s client %s (before boarding %s); capsule body server %s client %s; at the end: server copy %s, '
                   'client copy %s (both Walking on the ground, < 1 m apart: %s)' % (ej and ej['t'], ejc and ejc['t'], hl.get('server'), hl.get('client'),
                                                                                   pb, body.get('server'), body.get('client'), cs, cc, land_ok), {'char': ch[::5]})
        hc = self.D.get('hud_c') or {}
        ok3 = bool(hc) and self.hud_ok(hc, False)
        self.check('d3_hud_after_death', 'PASS' if ok3 else 'FAIL', 'client HUD 2 s after the death: %s (want no ship HUD, overlay back)' % hc)

    # ---- (e) ship 2: the client rides on the deck, the host boards and flies
    def start_spawn2(self):
        self.hchar.set_actor_rotation(unreal.Rotator(0.0, 0.0, 0.0), True)
        self.hpc.set_control_rotation(unreal.Rotator(0.0, 0.0, 0.0))
        self.D['before'] = set(s.get_name() for s in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.load_class(None, SHIP_CLS)))

    def ph_spawn2(self, el):
        if el >= 0.2 and 'cmd' not in self.D:
            self.D['cmd'] = True
            self.cmd(self.sw, 'Aura.Airship.Spawn')
        if el >= 1.5 and self.ship2_s is None:
            ss = [s for s in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.load_class(None, SHIP_CLS))
                  if s.get_name() not in self.D['before'] and not s.is_airship_dead()]
            if ss:
                self.ship2_s = ss[0]
                # AS45_SCHEME on ship 2 too, on the server, before anyone uses it (the host presses F on it about 6 s later)
                self.R.setdefault('setup', {})['scheme_ship2'] = self.set_scheme(self.ship2_s, 'ship 2')
        if el >= 2.0 and self.ship2_s is not None and self.ship2_c is None:
            p = v3(self.ship2_s.get_actor_location())
            cs = [s for s in unreal.GameplayStatics.get_all_actors_of_class(self.cw, unreal.load_class(None, SHIP_CLS)) if not s.is_airship_dead()]
            if cs:
                self.ship2_c = min(cs, key=lambda s: dist(v3(s.get_actor_location()), p))

    def end_spawn2(self):
        ok = self.ship2_s is not None and self.ship2_c is not None
        self.check('e0_spawn2', 'PASS' if ok else 'FAIL', 'Aura.Airship.Spawn: server %s at %s, client copy %s at %s' % (
            self.ship2_s.get_name() if self.ship2_s else None, r(v3(self.ship2_s.get_actor_location()), 0) if self.ship2_s else None,
            self.ship2_c.get_name() if self.ship2_c else None, r(v3(self.ship2_c.get_actor_location()), 0) if self.ship2_c else None))
        if not ok:
            self.finish('no second ship')
            return
        # F-E record: the scheme ship 2 runs on both machines (the client copy has it once OnRep_ControlScheme arrived)
        sc = {}
        for tag, ship in (('server', self.ship2_s), ('client', self.ship2_c)):
            try:
                sc[tag] = en(ship.get_control_scheme())
            except Exception as e:  # noqa: BLE001
                sc[tag] = 'n/a %r' % e
        self.R.setdefault('setup', {})['scheme_ship2_both'] = sc
        self.line('INFO', 'ship 2 control scheme (end of spawn2): %s' % sc)
        self.mesh_rest('server', self.ship2_s)
        self.mesh_rest('client', self.ship2_c)

    def start_deck2(self):
        yaw = self.ship2_s.get_actor_rotation().yaw
        loc, tr1 = self.deck_point(self.ship2_s, -250.0, self.cchar_s)
        self.tp([self.cchar_s, self.cchar_c], loc, yaw)
        loc2, tr2 = self.deck_point(self.ship2_s, 250.0, self.hchar)
        self.tp([self.hchar], loc2, yaw)
        self.line('INFO', 'client onto ship 2\'s deck at %s (trace %s), host at %s (trace %s)' % (r(loc, 0), tr1, r(loc2, 0), tr2))

    def ph_deck2(self, el):
        if el >= 3.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.sw, 'deck2', 'deck', self.ship2_s)
            self.capture(self.cw, 'deck2', 'deck', self.ship2_c)

    def end_deck2(self):
        s = self.ser('deck2')[-1]
        ok = all(s.get(k) and s[k]['mode'] == 'MOVE_WALKING' and s[k]['coll'] == 'QUERY_ONLY' and s[k].get('rider') for k in ('cs', 'cc', 'hs'))
        self.check('e1_two_on_deck', 'PASS' if ok else 'FAIL', 'ship 2 deck: client character server copy %s, client copy %s; host %s; '
                   'host as seen by the client %s' % (s.get('cs'), s.get('cc'), s.get('hs'), s.get('hc')), s)

    def ph_host_board(self, el):
        if el >= 0.2 and 'f' not in self.D:
            self.D['f'] = True
            self.inject('server', 'IA_AirshipBoard')
            self.event('inject', what='IA_AirshipBoard (host)')
        if el >= 1.2 and 'fb' not in self.D and not self.ship2_s.has_pilot():
            self.D['fb'] = True
            self.hpc.get_component_by_class(unreal.load_class(None, '/Script/Aura.AirshipPilotComponent')).request_board()
            self.line('WARN', 'host F injection did not board in 1 s: fallback RequestBoard (host)')
        if el >= 2.2 and 'hud' not in self.D:
            self.D['hud'] = True
            self.D['hud_h'] = self.hud(self.hpc, self.ship2_s)
            self.D['hud_c'] = self.hud(self.cpc, self.ship2_c)
            self.xgrab('host_flying', 'both')

    def end_host_board(self):
        ok = same(self.ship2_s.get_pilot(), self.hchar) and same(self.hpc.get_controlled_pawn(), self.ship2_s) and self.ship2_c.has_pilot() and not self.D.get('fb')
        hh, hc = self.D.get('hud_h') or {}, self.D.get('hud_c') or {}
        s = self.ser('host_board')[-1]
        ok_c = s.get('cs') and s.get('cc') and s['cs'].get('rider') and s['cc'].get('rider') and s['cs']['coll'] == 'QUERY_ONLY' and s['cc']['coll'] == 'QUERY_ONLY'
        self.check('e2_host_board', 'PASS' if (ok and ok_c) else 'FAIL', 'host F on ship 2 while the client rides: host boarded %s%s; client still '
                   'a rider (server copy %s, client copy %s)' % (ok, ' (fallback)' if self.D.get('fb') else '', s.get('cs'), s.get('cc')))
        ok2 = bool(hh) and self.hud_ok(hh, True) and bool(hc) and self.hud_ok(hc, False)
        self.check('e3_hud_host_flying', 'PASS' if ok2 else 'FAIL', 'host HUD %s (want ship HUD, overlay collapsed); client HUD %s (want on foot)' % (hh, hc))

    def ph_host_fly(self, el):
        for t, name, inp in HOST_FLY:
            if el >= t and name not in self.D:
                self.D[name] = r(self.now, 3)
                self.ship2_s.debug_set_input(*inp)
                self.event('host_input', step=name, input=inp)
        if el >= 7.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture(self.sw, 'host_fly', 'deck', self.ship2_s)
            self.capture(self.cw, 'host_fly', 'deck', self.ship2_c)
            self.capture(self.cw, 'host_fly_client_view', 'player')

    def end_host_fly(self):
        try:
            self.ship2_s.debug_clear_input()
        except Exception:  # noqa: BLE001
            pass
        ss = [s for s in self.ser('host_fly') if s.get('S') and s.get('cs') and s.get('cc')]
        neu = [s for s in ss if s['el'] < 4.0]
        z = [s['S']['loc'][2] for s in neu]
        vz = [abs(s['S'].get('VerticalSpeedMS') or 0) for s in neu]
        pit = [abs(s['S'].get('PitchDeg') or 0) for s in neu]
        sink_ok = bool(z) and (max(z) - min(z)) < 50.0 and max(vz) < 0.3 and max(pit) < 1.5
        out = {}
        for key, c in (('server', 'cs'), ('client', 'cc')):
            loc = [s[c].get('local') for s in ss if s[c].get('local')]
            out[key] = {'x_m': (r(min(l[0] for l in loc) / 100.0, 2), r(max(l[0] for l in loc) / 100.0, 2)) if loc else None,
                        'y_m': (r(min(l[1] for l in loc) / 100.0, 2), r(max(l[1] for l in loc) / 100.0, 2)) if loc else None,
                        'z_m': (r(min(l[2] for l in loc) / 100.0, 2), r(max(l[2] for l in loc) / 100.0, 2)) if loc else None,
                        'rider_frac': r(sum(1 for s in ss if s[c].get('rider')) / max(1, len(ss)), 3),
                        'query_only_frac': r(sum(1 for s in ss if s[c].get('coll') == 'QUERY_ONLY') / max(1, len(ss)), 3),
                        'walking_frac': r(sum(1 for s in ss if s[c].get('mode') == 'MOVE_WALKING') / max(1, len(ss)), 3),
                        'base_frac': r(sum(1 for s in ss if s[c].get('base') == (self.ship2_s.get_name() if key == 'server' else self.ship2_c.get_name())) / max(1, len(ss)), 3)}
        dl = [dist(s['cs']['local'], s['cc']['local']) for s in ss if s['cs'].get('local') and s['cc'].get('local')]
        out['server_vs_client_local_cm'] = stats(dl)
        top = max((s['S'].get('ForwardSpeedMS') or 0) for s in ss) if ss else 0
        aboard = all(out[k]['z_m'] and out[k]['z_m'][0] > 2.0 and out[k]['z_m'][1] < 8.0 and out[k]['rider_frac'] >= 0.98
                     and out[k]['query_only_frac'] >= 0.98 for k in ('server', 'client'))
        e = self.errors('host_fly')
        self.R['mp']['err_host_fly'] = e
        ok = sink_ok and aboard
        self.check('e4_host_fly_rider', 'PASS' if ok else 'FAIL', 'host flies ship 2 (neutral 4 s, throttle 0.5, turn, brake; top %.1f m/s) with the '
                   'client on deck: neutral part z span %.1f cm, |vz| max %.2f m/s, |pitch| max %.2f deg (no sink: %s); client character in '
                   'ship-2 space per machine %s (aboard: %s); ship 2 server vs client position error %s cm (the client sees the host\'s '
                   'ship)' % (top, (max(z) - min(z)) if z else -1, max(vz) if vz else -1, max(pit) if pit else -1, sink_ok, out, aboard,
                              e and e['pos']), {'rider': out, 'err': e})

    # ---- report helpers
    def summary(self):
        return dict((k, v['status']) for k, v in self.R['checks'].items())


def write_mp_report(R):
    try:
        L = ['Airship multiplayer PIE test (%s), armed %s, game time %.1f s, wall %.0f s, reason: %s' % (
            R['version'], R['armed_utc'], R.get('game_t', 0), R.get('wall_s', 0), R.get('reason'))]
        L.append('play settings %s; setup %s' % (R.get('play_settings'), R.get('setup')))
        L.append('mp: %s' % dict((k, v) for k, v in R['mp'].items() if not k.startswith(('lat_', 'err_'))))
        n = {'PASS': 0, 'FAIL': 0, 'WARN': 0}
        for k, c in R['checks'].items():
            n[c['status']] = n.get(c['status'], 0) + 1
        L.append('checks: %s' % n)
        L.append('')
        for k, c in R['checks'].items():
            L.append('%s %s [t %s]: %s' % (c['status'], k, c['t'], c['summary']))
            L.append('')
        for ph in ('fly0', 'fly1'):
            L.append('response delays %s (s after the client input): %s' % (ph, json.dumps(R['mp'].get('lat_' + ph))))
        for ph in ('hover', 'fly0', 'fly1', 'host_fly'):
            L.append('server vs client %s: %s' % (ph, json.dumps(R['mp'].get('err_' + ph))))
        L.append('')
        L.append('script errors %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        for k, v in R['errors'].items():
            L.append('--- %s\n%s' % (k, v['last'][-900:]))
        for k, v in (R.get('log_scan') or {}).items():
            L.append('log %s: %d' % (k, v['count']))
            for s in v['sample'][:6]:
                L.append('    %s' % s[:300])
        L.append('log per phase: %s' % json.dumps(R.get('log_segments')))
        L.append('captures: %s' % [s['file'] for s in R['shots']])
        L.append('x grabs: %s' % R['xgrabs'])
        L.append('')
        L.append('series (2 Hz): t phase | server ship loc vel | client ship loc | err cm | S thr steer yawrate fwd | C thr steer | wheel S/C | health S/C | client char S/C')
        last = -1
        for s in R['series']:
            if int(s['t'] * 2) == last:
                continue
            last = int(s['t'] * 2)
            S, C = s.get('S') or {}, s.get('C') or {}
            e = dist(S['loc'], C['loc']) if S.get('loc') and C.get('loc') else None
            L.append('%6.1f %-10s | %s %s | %s | %s | %s %s %s %s | %s %s | %s/%s | %s/%s | %s / %s' % (
                s['t'], s['ph'], S.get('loc'), S.get('vel'), C.get('loc'), r(e, 1) if e is not None else None, S.get('Throttle'), S.get('Steer'),
                S.get('YawRateDegS'), S.get('ForwardSpeedMS'), C.get('Throttle'), C.get('Steer'), (S.get('anim') or {}).get('WheelAngleDeg'),
                (C.get('anim') or {}).get('WheelAngleDeg'), S.get('Health'), C.get('Health'),
                (s.get('cs') or {}).get('local'), (s.get('cc') or {}).get('local')))
        with open(os.path.join(MP, 'mp_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        with open(os.path.join(MP, 'mp_report.txt'), 'w') as f:
            f.write('report failed: %s' % traceback.format_exc())


if 'AS45_RUN' in globals() and AS45_RUN is not None and AS45_RUN.phase not in ('finished',):
    print('FAIL: a run is active (phase %s): not armed again' % AS45_RUN.phase)
else:
    AS45_RUN = MpRun()
    if not AS45_RUN.arm():
        AS45_RUN.restore()
        AS45_RUN.remove_temp()
        AS45_RUN.phase = 'finished'
    print('\n'.join(AS45_RUN.R['lines']))
