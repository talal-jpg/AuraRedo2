# as_30_pie_smoke.py - first PIE smoke test of the drivable airship on L_AirshipTest (Standalone, 1 player), session 3.
# Run through the clone editor's inbox (the editor must have L_AirshipTest open, no PIE running):
#   Docs/Airship/scripts/harness/inbox.sh 30 Docs/Airship/scripts/ue/as_30_pie_smoke.py 120
# It arms a frame-by-frame state machine (Slate post-tick callback, as the Burrower / Mech Sentinel harnesses), starts PIE
# and returns at once; the world ticks between inbox calls. Status any time: inbox.sh 31 as_31_pie_status.py.
# Results: Saved/Airship/pie_result.json (checks a..k with numbers, 10 Hz telemetry, events), pie_smoke.txt (readable),
#          Saved/Airship/captures/*.png (TEMP_AS_Capture scene captures).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30 (game time stays right when the editor is on a
# hidden i3 workspace), LevelEditorPlaySettings Standalone / 1 player, UBurrowerSettings.bEnabled False (no Burrower
# chasing the test pilot). One TEMP_AS_Capture SceneCapture2D in the editor level (removed after PIE; the map is never
# saved by this script). The user's own Play ("Repeating last play command" in the log) is never stopped.
#
# Timeline (game seconds; each phase starts when the previous one ends):
#  settle 3   -> board (Aura.Airship.Board)               (a) possessed + attached at PilotSeat
#  hover 10   neutral input                                (b) altitude drift, attitude
#  cannons 9  look port, RequestFire; look stbd, fire      (i) balls from the muzzles, recoil in the bones, wall hits
#  exit 3     Aura.Airship.Exit (pilot hurt by 25 first)   (k) character back, Health/Mana = the saved values
#                                                          (k2) capsule keeps a QueryOnly body, stands on the hull 2 s
#  board2 2   Aura.Airship.Board
#  lift 11    lift +1 4 s, -1 4 s, 0 3 s                   (c)
#  throttle 10 throttle 1                                  (d) speed curve, top speed; (g) rig bones; (h) Niagara
#  steer 8    throttle 1 + steer +1 (D)                    (e) yaw rate sign, bank
#  boost 4 / brake 4                                       (f)
#  damage 3   Aura.Airship.Damage 500 x3                   (j1)
#  kill 16    Aura.Airship.Kill                            (j2) forces off, falls to the ground plane, wreck parts, pilot out
import json, math, os, time, traceback  # unreal = inbox namespace

AS30_VERSION = 'as_30_pie_smoke 2026-11-22'
OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
CAPS = os.path.join(OUT, 'captures')
MAP_NAME = 'L_AirshipTest'
SHIP_CLS = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'
BALL_CLS = '/Script/Aura.AirshipCannonball'
DMG_GE = '/Script/Aura.AirshipDamageEffect'
TEMP = 'TEMP_AS_Capture'
FIXED_FPS = 30.0
CANNONS = ['L1', 'L2', 'R1', 'R2']
PODS = ['FL', 'FR', 'RL', 'RR']
PHASES = [('settle', 3.0), ('board', 3.0), ('hover', 10.0), ('cannons', 9.0), ('exit', 3.0), ('board2', 2.0),
          ('lift', 11.0), ('throttle', 10.0), ('steer', 8.0), ('boost', 4.0), ('brake', 4.0), ('damage', 3.0),
          ('kill', 16.0)]
WREST = ['Thruster_FL', 'Thruster_RR', 'Turbine_L', 'Turbine_R', 'Rudder', 'SearchLight_AftL', 'SearchLight_FwdC',
         'Cannon_L1', 'Cannon_L1_Barrel', 'Cannon_R2', 'Turbine_L_Rod']
RIG_VARS = ['TurbineYawDeg_L', 'TurbineYawDeg_R', 'RotorAngleDeg_L', 'WheelAngleDeg', 'RudderDeg', 'NozzlePitchDeg_FL',
            'NozzleRollDeg_FL', 'NozzleFlareDeg_FL', 'NozzleFlareDeg_RR', 'ThrustAlpha_FL', 'CannonYawDeg_L1',
            'CannonElevDeg_L1', 'CannonRecoilCm_L1', 'CannonRecoilCm_L2', 'CannonRecoilCm_R1', 'CannonRecoilCm_R2',
            'SearchLightPanDeg', 'bIsDead', 'DeathTime']


# ----------------------------------------------------------------------------------------------------------- maths
def v3(v):
    return [float(v.x), float(v.y), float(v.z)]


def q4(q):
    return [float(q.x), float(q.y), float(q.z), float(q.w)]


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def qinv(q):
    return [-q[0], -q[1], -q[2], q[3]]


def qangle_axis(q):
    if q[3] < 0:
        q = [-x for x in q]
    w = max(-1.0, min(1.0, q[3]))
    ang = math.degrees(2.0 * math.acos(w))
    s = math.sqrt(max(0.0, 1.0 - w * w))
    return ang, ([q[0] / s, q[1] / s, q[2] / s] if s > 1e-9 else [0.0, 0.0, 0.0])


def signed_about(q, axis):
    """signed angle (deg) of q about a unit axis (twist part)"""
    p = q[0] * axis[0] + q[1] * axis[1] + q[2] * axis[2]
    tw = [axis[0] * p, axis[1] * p, axis[2] * p, q[3]]
    n = math.sqrt(sum(x * x for x in tw))
    if n < 1e-12:
        return 0.0
    tw = [x / n for x in tw]
    ang, ax = qangle_axis(tw)
    return ang if (ax[0] * axis[0] + ax[1] * axis[1] + ax[2] * axis[2]) >= 0 else -ang


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def r(v, n=2):
    if isinstance(v, (list, tuple)):
        return [r(x, n) for x in v]
    return round(float(v), n) if isinstance(v, (int, float)) else v


def tl_get(obj, names):
    return json.loads(unreal.ToolsetLibrary.get_object_properties(obj, names))


def tl_set(obj, values):
    return unreal.ToolsetLibrary.set_object_properties(obj, json.dumps(values))


def gp(obj, *names, **kw):
    for n in names:
        try:
            return obj.get_editor_property(n)
        except Exception:  # noqa: BLE001
            continue
    return kw.get('default')


def valid(a):
    try:
        return a is not None and unreal.SystemLibrary.is_valid(a)
    except Exception:  # noqa: BLE001
        return False


def find_log():
    d = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Logs')
    p = os.path.join(d, 'Aura.log')
    return p if os.path.exists(p) else None


def parse_struct(txt):
    """'(A=1.0,B=True,...)' -> dict (flat FAirshipFlightTelemetry export)"""
    out = {}
    s = txt.strip()[1:-1]
    for part in s.split(','):
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        if v in ('True', 'False'):
            out[k] = v == 'True'
        else:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


# ----------------------------------------------------------------------------------------------------------- run
class AsRun(object):
    def __init__(self):
        self.R = {'version': AS30_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'checks': {}, 'events': [], 'series': [], 'errors': {}, 'lines': [], 'shots': [], 'done': False}
        self.orig = {}
        self.handle = None
        self.phase = 'arming'
        self.pi = -1
        self.p_t0 = 0.0
        self.w = None
        self.pc = None
        self.char = None
        self.ship = None
        self.mesh = None
        self.anim = None
        self.now = 0.0
        self.t_world0 = None
        self.wall0 = time.time()
        self.last_sample = -1.0
        self.last_write = 0.0
        self.D = {}               # per-phase scratch
        self.rest = {}            # component-space rest transforms of bones (first sample)
        self.balls = {}
        self.cap = None
        self.cap_dead = False
        self.ncap = 0
        self.log_file = None
        self.log_off = 0
        self.user_play = False
        self.health_attr = unreal.GameplayAttribute()
        self.health_attr.import_text('(AttributeName="Health",Attribute=/Script/Aura.MyAttributeSet:Health,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")')
        self.mana_attr = unreal.GameplayAttribute()
        self.mana_attr.import_text('(AttributeName="Mana",Attribute=/Script/Aura.MyAttributeSet:Mana,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")')
        self.maxh_attr = unreal.GameplayAttribute()
        self.maxh_attr.import_text('(AttributeName="MaxHealth",Attribute=/Script/Aura.MyAttributeSet:MaxHealth,AttributeOwner="/Script/CoreUObject.Class\'/Script/Aura.MyAttributeSet\'")')

    # ---------------------------------------------------------------- output
    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.phase, msg)
        self.R['lines'].append(s)
        print(s)
        try:
            with open(os.path.join(OUT, 'pie_log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def check(self, key, status, msg, data=None):
        self.R['checks'][key] = {'status': status, 'summary': msg, 'data': data, 't': r(self.now)}
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
        if not force and time.time() - self.last_write < 2.0:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        try:
            with open(os.path.join(OUT, 'pie_result.json'), 'w') as f:
                json.dump(self.R, f, indent=1, default=str)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- arm
    def arm(self):
        os.makedirs(CAPS, exist_ok=True)
        with open(os.path.join(OUT, 'pie_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s\n' % (AS30_VERSION, self.R['armed_utc']))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open the map first' % (ew.get_path_name(), MAP_NAME))
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = r(mem, 1)
            self.line('INFO' if mem >= 4 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        # in-memory changes (originals kept for the restore)
        try:
            eng = unreal.find_object(None, '/Engine/Transient.UnrealEdEngine_0')
            self.orig['engine'] = tl_get(eng, ['bUseFixedFrameRate', 'FixedFrameRate'])
            tl_set(eng, {'bUseFixedFrameRate': True, 'FixedFrameRate': FIXED_FPS})
            self.line('INFO', 'fixed frame rate %.0f (was %s)' % (FIXED_FPS, self.orig['engine']))
        except Exception:  # noqa: BLE001
            self.err('fixed_fps')
        try:
            ps = unreal.get_default_object(unreal.load_class(None, '/Script/UnrealEd.LevelEditorPlaySettings'))
            self.orig['play'] = tl_get(ps, ['PlayNetMode', 'PlayNumberOfClients', 'RunUnderOneProcess'])
            tl_set(ps, {'PlayNetMode': 'PIE_Standalone', 'PlayNumberOfClients': 1})
            self.line('INFO', 'play settings Standalone / 1 player (were %s)' % self.orig['play'])
        except Exception:  # noqa: BLE001
            self.err('play_settings')
        try:
            bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            self.orig['burrower_enabled'] = bool(bcdo.get_editor_property('bEnabled'))
            bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
            self.line('INFO', 'BurrowerSettings.bEnabled False for the run (was %s)' % self.orig['burrower_enabled'])
        except Exception:  # noqa: BLE001
            self.err('burrower_settings')
        try:
            for a in eas.get_all_level_actors():
                if a.get_actor_label().startswith(TEMP):
                    eas.destroy_actor(a)
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, -6000, 3000))
            cap.set_actor_label(TEMP)
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
            self.line('INFO', 'placed %s in the editor level (removed after PIE, the map is not saved)' % TEMP)
        except Exception:  # noqa: BLE001
            self.err('temp_capture')
            self.cap_dead = True
        self.log_file = find_log()
        if self.log_file:
            self.log_off = os.path.getsize(self.log_file)
        with open(os.path.join(OUT, 'pie_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write(True)
        self.line('INFO', 'armed; PIE requested')
        return True

    # ---------------------------------------------------------------- restore / finish
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
        if self.phase == 'finished':
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        try:
            if self.ship is not None and valid(self.ship):
                self.ship.debug_clear_input()
        except Exception:  # noqa: BLE001
            pass
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.scan_log()
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
        write_report(self.R)
        self.line('INFO', 'done; results in pie_result.json / pie_smoke.txt')

    def scan_log(self):
        if not self.log_file:
            return
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                txt = f.read()
            lines = txt.splitlines()
            pats = {'airship': 'LogAirship', 'error': 'Error:', 'ensure': 'Ensure condition failed', 'warning_cr': 'LogControlRig',
                    'rigphysics': 'LogRigPhysics', 'user_play': 'Repeating last play command', 'accessed_none': 'Accessed None'}
            sc = {}
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                sc[k] = {'count': len(hit), 'sample': hit[:12] + (hit[-6:] if len(hit) > 18 else [])}
            self.R['log_scan'] = sc
            if sc['user_play']['count']:
                self.user_play = True
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    # ---------------------------------------------------------------- PIE helpers
    def cmd(self, c):
        unreal.SystemLibrary.execute_console_command(self.w, c)
        self.event('cmd', cmd=c)
        self.line('INFO', 'console: %s' % c)

    def tele(self):
        try:
            return parse_struct(self.ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def bone(self, b):
        t = self.mesh.get_socket_transform(b, unreal.RelativeTransformSpace.RTS_COMPONENT)
        return v3(t.translation), q4(t.rotation)

    def anim_vals(self):
        out = {}
        if self.anim is None:
            return out
        for n in RIG_VARS:
            try:
                v = self.anim.get_editor_property(n)
                out[n] = bool(v) if isinstance(v, bool) else round(float(v), 3)
            except Exception:  # noqa: BLE001
                out[n] = None
        return out

    def rig_bones(self):
        """bone-derived values to compare with the anim instance (kinematic bones: should match exactly)"""
        out = {}
        try:
            hl = self.bone('Hull')[1]
            tl = self.bone('Turbine_L')[1]
            ro = self.bone('Turbine_L_Rotor')[1]
            out['TurbineYawDeg_L'] = signed_about(qmul(qinv(hl), tl), [0, 0, 1])
            out['RotorAngleDeg_L'] = signed_about(qmul(qinv(tl), ro), [1, 0, 0]) % 360.0
            hw = self.bone('Helm')[1]
            wh = self.bone('Helm_Wheel')[1]
            out['WheelAngleDeg_mod360'] = signed_about(qmul(qinv(hw), wh), [1, 0, 0])
            ru = self.bone('Rudder')[1]
            out['RudderDeg'] = signed_about(qmul(qinv(hl), ru), [0, 0, 1])
            pod = self.bone('Thruster_FL')[1]
            nz = self.bone('Thruster_FL_Nozzle')[1]
            rel = qmul(qinv(pod), nz)
            out['NozzlePitchDeg_FL'] = signed_about(rel, [0, 1, 0])
            out['NozzleRollDeg_FL'] = signed_about(rel, [1, 0, 0])
            pt = self.bone('Thruster_FL_Petal03')[1]
            out['NozzleFlareDeg_FL_abs'] = qangle_axis(qmul(qinv(nz), pt))[0]
            c = self.bone('Cannon_L1')
            out['Cannon_L1_pos'] = c[0]
        except Exception:  # noqa: BLE001
            self.err('rig_bones')
        return out

    def health(self, a):
        try:
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(a)
            if asc is None:
                return None, None, None
            vals = []
            for at in (self.health_attr, self.mana_attr, self.maxh_attr):
                x = asc.get_gameplay_attribute_value(at)
                vals.append(round(float(x[0] if isinstance(x, tuple) else x), 2))
            return tuple(vals)
        except Exception:  # noqa: BLE001
            self.err('health')
            return None, None, None

    def pawn(self):
        try:
            return self.pc.get_controlled_pawn()
        except Exception:  # noqa: BLE001
            return None

    def fx_vals(self):
        out = {}
        for c in ('ThrusterFX_FL', 'ThrusterFX_RR', 'TurbineFX_L'):
            try:
                nc = self.ship.get_editor_property(c)
                for p in ('Thrust', 'Boost'):
                    got = None
                    for name in (p, 'User.' + p):
                        x = nc.get_variable_float(name)
                        val, ok = (x if isinstance(x, tuple) else (x, True))
                        if ok:
                            got = round(float(val), 3)
                            break
                    out['%s.%s' % (c, p)] = got
                out['%s.active' % c] = bool(nc.is_active())
            except Exception:  # noqa: BLE001
                self.err('fx_vals')
        return out

    def ship_loc(self):
        return v3(self.ship.get_actor_location())

    def sample(self, force=False):
        if not force and self.now - self.last_sample < 0.1:
            return None
        self.last_sample = self.now
        try:
            t = self.tele()
            ro = self.ship.get_actor_rotation()
            s = {'t': r(self.now), 'ph': self.phase, 'loc': r(self.ship_loc(), 1), 'rpy': r([ro.roll, ro.pitch, ro.yaw], 2),
                 'vel': r(v3(self.ship.get_velocity()), 1)}
            for k in ('SpeedMS', 'ForwardSpeedMS', 'LateralSpeedMS', 'AltitudeM', 'GroundClearanceM', 'VerticalSpeedMS',
                      'YawRateDegS', 'RollDeg', 'PitchDeg', 'YawDeg', 'HoldAltitudeM', 'BoostFuel', 'Health',
                      'Throttle', 'Steer', 'Lift', 'Boost', 'bBraking', 'bHasPilot', 'bIsDead', 'MassKg'):
                if k in t:
                    s[k] = r(t[k], 3) if isinstance(t[k], float) else t[k]
            if self.phase in ('exit', 'board2', 'settle'):
                cm = gp(self.char, 'character_movement', 'CharacterMovement')
                base = self.char.get_movement_base() if hasattr(self.char, 'get_movement_base') else None
                s['char'] = {'loc': r(v3(self.char.get_actor_location()), 1),
                             'mode': str(cm.get_editor_property('movement_mode')) if cm else None,
                             'base': base.get_name() if base else None,
                             'mass': gp(cm, 'mass') if cm else None}
            if self.phase in ('throttle', 'steer', 'boost', 'brake', 'lift', 'hover', 'kill'):
                s['anim'] = self.anim_vals()
                s['bones'] = r(self.rig_bones(), 3)
                s['fx'] = self.fx_vals()
            self.R['series'].append(s)
            return s
        except Exception:  # noqa: BLE001
            self.err('sample')
            return None

    # ---------------------------------------------------------------- captures
    def capture(self, label, kind):
        if self.cap_dead or self.ncap >= 14:
            return None
        try:
            if self.cap is None:
                caps = [a for a in unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.SceneCapture2D) if TEMP in a.get_actor_label()]
                if not caps:
                    self.cap_dead = True
                    self.line('WARN', 'no %s in the PIE world: no captures' % TEMP)
                    return None
                rt = unreal.RenderingLibrary.create_render_target2d(self.w, 1600, 900, unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = caps[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('capture_every_frame', False)
                cc.set_editor_property('capture_on_movement', False)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.cap = (caps[0], cc, rt)
            a, cc, rt = self.cap
            loc = self.ship_loc()
            fwd = v3(self.ship.get_actor_forward_vector())
            rgt = v3(self.ship.get_actor_right_vector())
            up = [0.0, 0.0, 1.0]
            fov = 60.0

            def at(f, rr, u):
                return [loc[i] + fwd[i] * f + rgt[i] * rr + up[i] * u for i in range(3)]
            if kind == 'player':
                cm = unreal.GameplayStatics.get_player_camera_manager(self.w, 0)
                frm, rot, fov = v3(cm.get_camera_location()), cm.get_camera_rotation(), cm.get_fov_angle()
            else:
                if kind == 'side':
                    frm, to = at(2500, -5200, 1400), at(-300, 0, 0)
                elif kind == 'port':      # look at the port broadside from aft-starboard-above
                    frm, to = at(-4200, 2200, 2600), at(-300, -2600, 200)
                elif kind == 'stbd':
                    frm, to = at(-4200, -2200, 2600), at(-300, 2600, 200)
                elif kind == 'behind':
                    frm, to = at(-6500, -1200, 1800), at(400, 0, 0)
                elif kind == 'below':
                    frm, to = at(1200, -3800, -2200), at(-200, 0, -300)
                elif kind == 'wreck':
                    frm, to = at(3500, -6000, 3500), at(0, 0, -400)
                else:
                    return None
                rot = unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*frm), unreal.Vector(*to))
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(unreal.Vector(*frm), rot, False, True)
            cc.capture_scene()
            name = '%s_%s' % (label, kind)
            unreal.RenderingLibrary.export_render_target(self.w, rt, CAPS, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 't': r(self.now), 'file': os.path.join(CAPS, name + '.png')})
            self.line('INFO', 'capture %s' % name)
            return name
        except Exception:  # noqa: BLE001
            self.err('capture')
            self.cap_dead = True
            return None

    # ---------------------------------------------------------------- cannonballs
    def track_balls(self):
        try:
            cls = unreal.load_class(None, BALL_CLS)
            for b in unreal.GameplayStatics.get_all_actors_of_class(self.w, cls):
                k = b.get_name()
                rec = self.balls.get(k)
                p = v3(b.get_actor_location())
                hid = bool(gp(b, 'hidden', 'bHidden', default=False))
                if rec is not None and rec.get('last') and dist(p, rec['last']) < 2.0 and self.now - rec.get('t_last', 0) > 0.0:
                    hid = True          # stopped moving (impact)
                if rec is None:
                    rec = {'first': r(p, 1), 't0': r(self.now), 'phase': self.phase, 'side': self.D.get('side')}
                    self.balls[k] = rec
                if not rec.get('hidden'):
                    rec['last'] = r(p, 1)
                    rec['t_last'] = r(self.now)
                    if hid:
                        rec['hidden'] = True
                        rec['t_hit'] = r(self.now)
                rec['seen'] = r(self.now)
            for k, rec in self.balls.items():
                if rec.get('seen') != r(self.now) and not rec.get('gone'):
                    rec['gone'] = r(self.now)
        except Exception:  # noqa: BLE001
            self.err('balls')

    # ---------------------------------------------------------------- the state machine
    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if sum(e['n'] for e in self.R['errors'].values()) > 200:
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
            ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
            if ws:
                self.w = ws[0]
                self.phase = 'wait_pawn'
                self.line('INFO', 'PIE world %s' % self.w.get_path_name())
            elif time.time() - self.wall0 > 180:
                self.finish('PIE did not start in 180 s')
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        tw = unreal.GameplayStatics.get_time_seconds(self.w)
        if self.t_world0 is None:
            self.t_world0 = tw
        self.now = tw - self.t_world0
        if self.phase == 'wait_pawn':
            self.pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
            p = self.pawn() if self.pc else None
            ships = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, SHIP_CLS))
            if p is not None and ships:
                self.char = p
                self.ship = ships[0]
                self.mesh = self.ship.get_editor_property('Mesh')
                self.anim = self.mesh.get_anim_instance()
                self.mesh.set_editor_property('visibility_based_anim_tick_option',
                                              unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES,
                                              unreal.PropertyAccessChangeNotifyMode.NEVER)
                self.R['setup'] = {'char': p.get_class().get_name(), 'ship': self.ship.get_name(), 'ships': len(ships),
                                   'anim': self.anim.get_class().get_name() if self.anim else None,
                                   'debug_die': gp(p, 'DebugDieAfterBeginPlaySeconds')}
                self.line('INFO', 'setup %s' % self.R['setup'])
                for b in WREST + ['Hull', 'Cannon_L2', 'Cannon_R1', 'Helm', 'Helm_Wheel']:
                    self.rest[b] = self.bone(b)
                self.next_phase()
            elif self.now > 20:
                self.finish('no player pawn / ship after 20 s (pawn %s, ships %d)' % (p, len(ships)))
            return
        self.scan_user_play()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        if not valid(self.ship):
            self.finish('the ship is gone')
            return
        self.sample()
        if self.phase != 'kill':
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
            self.next_phase()

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

    def next_phase(self):
        self.pi += 1
        if self.pi >= len(PHASES):
            self.finish('all phases done')
            return
        self.phase = PHASES[self.pi][0]
        self.p_t0 = self.now
        self.D = {}
        self.line('INFO', 'phase %s (%.0f s)' % (self.phase, PHASES[self.pi][1]))
        try:
            getattr(self, 'start_' + self.phase, lambda: None)()
        except Exception:  # noqa: BLE001
            self.err('start_' + self.phase)

    # ---- settle
    def start_settle(self):
        self.ship.debug_clear_input()
        self.R['char_start'] = {'health': self.health(self.char), 'loc': r(v3(self.char.get_actor_location()), 1)}
        # hurt the character by 25 first, so 'restored at exit' can be told apart from a refill to MaxHealth
        try:
            ge = unreal.load_class(None, DMG_GE)
            tag = unreal.GameplayTag()
            tag.import_text('(TagName="SetDamageByCaller")')
            asc = unreal.AbilitySystemLibrary.get_ability_system_component(self.char)
            ctx = asc.make_effect_context()
            spec = asc.make_outgoing_spec(ge, 1.0, ctx)
            spec = unreal.AbilitySystemLibrary.assign_tag_set_by_caller_magnitude(spec, tag, 25.0)
            asc.apply_gameplay_effect_spec_to_self(spec)
            self.line('INFO', 'character hurt by 25 (AirshipDamageEffect on its own ASC) before boarding')
        except Exception:  # noqa: BLE001
            self.err('hurt_pilot')

    def ph_settle(self, el):
        pass

    # ---- (a) board
    def start_board(self):
        self.R['pre_board'] = self.health(self.char)
        self.line('INFO', 'character Health/Mana/MaxHealth before boarding %s' % (self.R['pre_board'],))
        self.cmd('Aura.Airship.Board')

    def ph_board(self, el):
        if 'possessed_t' not in self.D and self.pawn() == self.ship:
            self.D['possessed_t'] = el

    def end_board(self):
        seat = v3(self.ship.get_pilot_seat_location())
        cl = v3(self.char.get_actor_location())
        par = self.char.get_attach_parent_actor()
        caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
        hh = caps.get_scaled_capsule_half_height() if caps else 0.0
        foot = [cl[0], cl[1], cl[2] - hh]
        d = dist(foot, seat)
        ok = (self.pawn() == self.ship and bool(self.ship.has_pilot()) and self.ship.get_pilot() == self.char and par == self.ship
              and d < 30.0)
        self.check('a_board', 'PASS' if ok else 'FAIL', 'possessed %s after %.2f s, HasPilot %s, pilot is the character %s, '
                   'attached to %s, pilot feet %.1f cm from the PilotSeat %s (capsule half height %.0f)'
                   % (self.pawn() == self.ship, self.D.get('possessed_t', -1), self.ship.has_pilot(),
                      self.ship.get_pilot() == self.char, par.get_name() if par else None, d, r(seat, 1), hh),
                   {'seat': r(seat, 1), 'char': r(cl, 1), 'feet_to_seat': r(d), 'possessed_t': self.D.get('possessed_t')})
        self.capture('board', 'player')

    # ---- (b) hover
    def start_hover(self):
        self.ship.debug_clear_input()
        self.D['t0'] = self.tele()
        self.D['loc0'] = self.ship_loc()

    def ph_hover(self, el):
        if 2.95 < el < 3.05 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('hover', 'side')
            self.capture('hover', 'player')
            self.capture('hover', 'below')

    def end_hover(self):
        ss = [s for s in self.R['series'] if s['ph'] == 'hover' and s['t'] >= self.p_t0 + 3.0]
        if not ss:
            self.check('b_hover', 'FAIL', 'no samples')
            return
        alts = [s['AltitudeM'] for s in ss]
        rolls = [abs(s['RollDeg']) for s in ss]
        pitches = [abs(s['PitchDeg']) for s in ss]
        vs = [abs(s['VerticalSpeedMS']) for s in ss]
        drift = dist(self.ship_loc(), self.D['loc0']) / 100.0
        a0 = self.D['t0'].get('AltitudeM')
        ok = (max(alts) - min(alts) < 1.0 and max(rolls) < 2.0 and max(pitches) < 2.0 and drift < 3.0)
        self.check('b_hover', 'PASS' if ok else 'FAIL', 'neutral 10 s (last 7 s): altitude %.2f..%.2f m (start %.2f, hold %.2f), '
                   '|roll| max %.2f, |pitch| max %.2f deg, |vz| max %.2f m/s, position drift %.2f m in 10 s'
                   % (min(alts), max(alts), a0 or 0, ss[-1].get('HoldAltitudeM', 0), max(rolls), max(pitches), max(vs), drift),
                   {'alt_min': min(alts), 'alt_max': max(alts), 'roll_max': max(rolls), 'pitch_max': max(pitches), 'drift_m': drift})

    # ---- (i) cannons
    def look(self, side):
        y = self.ship.get_actor_rotation().yaw + (-90.0 if side == 'port' else 90.0)
        self.pc.set_control_rotation(unreal.Rotator(0.0, -4.0, y))

    def start_cannons(self):
        self.D['side'] = 'port'
        self.look('port')
        self.D['n0'] = len(self.balls)
        self.D['recoil'] = {}

    def fire(self, side):
        self.D['side'] = side
        try:
            self.ship.request_fire()
            self.event('fire', side=side)
            self.line('INFO', 'RequestFire (%s)' % side)
        except Exception:  # noqa: BLE001
            self.err('request_fire')
        self.D['fire_t_' + side] = self.now

    def ph_cannons(self, el):
        if el < 1.6:
            self.look('port')
        if el >= 1.6 and 'fire_t_port' not in self.D:
            self.fire('port')
        if 3.6 < el < 5.2:
            self.look('stbd')
        if el >= 5.2 and 'fire_t_stbd' not in self.D:
            self.fire('stbd')
        for side, cs in (('port', ('L1', 'L2')), ('stbd', ('R1', 'R2'))):
            ft = self.D.get('fire_t_' + side)
            if ft is not None and self.now - ft <= 1.5:
                for c in cs:
                    try:
                        p = self.bone('Cannon_' + c)[0]
                        d = dist(p, self.rest['Cannon_' + c][0] if 'Cannon_' + c in self.rest else p)
                        rec = self.D['recoil'].setdefault(c, {'max_cm': 0.0, 't_max': None})
                        if d > rec['max_cm']:
                            rec['max_cm'] = round(d, 2)
                            rec['t_max'] = round(self.now - ft, 3)
                        av = self.anim_vals()
                        rec['anim_max'] = max(rec.get('anim_max', 0.0), av.get('CannonRecoilCm_' + c) or 0.0)
                    except Exception:  # noqa: BLE001
                        self.err('recoil')
                if 0.1 <= self.now - ft and 'cap_' + side not in self.D:
                    self.D['cap_' + side] = True
                    self.capture('cannons_' + side, side)

    def end_cannons(self):
        self.track_balls()
        res = {'balls': self.balls, 'recoil': self.D['recoil']}
        muzz = {}
        for c in CANNONS:
            try:
                muzz[c] = v3(self.mesh.get_socket_location('Cannon_%s_Muzzle' % c))
            except Exception:  # noqa: BLE001
                pass
        res['muzzles_now'] = r(muzz, 1)
        by_side = {'port': [], 'stbd': []}
        for k, b in self.balls.items():
            if b.get('side') in by_side:
                by_side[b['side']].append(b)
        msgs = []
        ok = True
        for side, wall_y in (('port', -9500.0 + 200.0), ('stbd', 14500.0 - 200.0)):
            bs = by_side[side]
            hits = [b for b in bs if b.get('last') and abs(b['last'][1] - wall_y) < 600.0]
            ok = ok and len(bs) == 2 and len(hits) >= 1
            msgs.append('%s: %d balls (first seen at %s), %d ended at the wall (y %.0f): last %s'
                        % (side, len(bs), [b['first'] for b in bs], len(hits), wall_y, [b.get('last') for b in bs]))
        rec = self.D['recoil']
        rok = all(rec.get(c, {}).get('max_cm', 0) > 20.0 for c in CANNONS)
        ok = ok and rok
        self.check('i_cannons', 'PASS' if ok else 'FAIL', '; '.join(msgs) + '; recoil in the bones (carriage max offset cm '
                   'from rest, anim CannonRecoilCm max): %s' % dict((c, (rec.get(c, {}).get('max_cm'), rec.get(c, {}).get('anim_max'), rec.get(c, {}).get('t_max'))) for c in CANNONS), res)

    # ---- (k) exit (the pilot is hurt first, so "restored" is not just a refill)
    def start_exit(self):
        self.D['before'] = self.health(self.char)
        self.cmd('Aura.Airship.Exit')

    def ph_exit(self, el):
        if 'back_t' not in self.D and self.pawn() == self.char:
            self.D['back_t'] = el
            self.D['after0'] = self.health(self.char)

    def end_exit(self):
        after = self.health(self.char)
        cl = v3(self.char.get_actor_location())
        par = self.char.get_attach_parent_actor()
        b0 = self.R.get('char_start', {}).get('health')
        pb = self.R.get('pre_board') or (None, None, None)
        ok = (self.pawn() == self.char and par is None and after[0] is not None and pb[0] is not None
              and abs(after[0] - pb[0]) < 0.5 and abs(after[1] - pb[1]) < 0.5 and not self.ship.has_pilot())
        self.check('k_exit', 'PASS' if ok else 'FAIL', 'character possessed again %s (after %.2f s), attached to %s; Health/Mana/'
                   'MaxHealth at start %s, at boarding (hurt by 25 first) %s, while flying %s, right after Exit %s, 3 s after %s '
                   '(want = at boarding, not refilled); character at %s (ship at %s), ship HasPilot %s'
                   % (self.pawn() == self.char, self.D.get('back_t', -1), par.get_name() if par else None, b0, pb,
                      self.D['before'], self.D.get('after0'), after, r(cl, 0), r(self.ship_loc(), 0), self.ship.has_pilot()),
                   {'start': b0, 'pre_board': pb, 'flying': self.D['before'], 'after': after, 'char_loc': r(cl, 1)})
        try:
            self.check_exit_body()
        except Exception:  # noqa: BLE001
            self.err('check_exit_body')
            self.check('k2_exit_body', 'FAIL', 'evaluation crashed: %s' % traceback.format_exc().strip().splitlines()[-1])
        self.capture('exit', 'side')

    def check_exit_body(self):
        # (k2) fix round 2 review: the ex-pilot's capsule keeps a physics body (QueryOnly; without a body the CMC sweeps
        # hit nothing and the character drops through the hull) and the character stands on the hull for the last 2 s
        caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
        hit, ce = None, None
        if caps is not None:
            c = self.char.get_actor_location()
            hh = caps.get_scaled_capsule_half_height()
            res = caps.line_trace_component(unreal.Vector(c.x, c.y, c.z + hh + 50.0), unreal.Vector(c.x, c.y, c.z - hh - 50.0),
                                            False, False, False)
            hit = bool(res[0] if isinstance(res, tuple) else res)
            ce = str(caps.get_collision_enabled())
        rel = [s['char']['loc'][2] - s['loc'][2] for s in self.R['series']
               if s.get('ph') == 'exit' and s.get('char') and s['t'] >= self.p_t0 + 1.0]
        cm = gp(self.char, 'character_movement', 'CharacterMovement')
        mode = str(cm.get_editor_property('movement_mode')) if cm else None
        riders = [p.get_name() for p in self.ship.get_passengers()]
        span = (max(rel) - min(rel)) if rel else None
        ok = (hit is True and 'QUERY_ONLY' in (ce or '') and len(rel) >= 10 and span < 30.0 and 'WALKING' in (mode or '')
              and self.char.get_name() in riders)
        self.check('k2_exit_body', 'PASS' if ok else 'FAIL', 'after Exit: line trace on the capsule alone hits %s (a body), '
                   'capsule collision %s (want QUERY_ONLY), character z - ship z over the last 2 s %s .. %s cm (%d samples, '
                   'span %s, want < 30: on the hull, not through it), movement %s, ship passengers %s'
                   % (hit, ce, r(min(rel), 1) if rel else None, r(max(rel), 1) if rel else None, len(rel),
                      r(span, 1) if span is not None else None, mode, riders),
                   {'trace_hit': hit, 'collision': ce, 'rel_z': r(rel, 1), 'mode': mode, 'passengers': riders})

    # ---- board again
    def start_board2(self):
        self.cmd('Aura.Airship.Board')

    def ph_board2(self, el):
        pass

    def end_board2(self):
        ok = self.pawn() == self.ship
        self.check('a2_board_again', 'PASS' if ok else 'FAIL', 'boarded again: possessed %s' % ok)

    # ---- (c) lift
    def start_lift(self):
        self.D['z0'] = self.ship_loc()[2]
        self.ship.debug_set_input(0.0, 0.0, 1.0, 0.0, False, False)

    def ph_lift(self, el):
        if el >= 4.0 and 'down' not in self.D:
            self.D['down'] = True
            self.D['z_up'] = self.ship_loc()[2]
            self.ship.debug_set_input(0.0, 0.0, -1.0, 0.0, False, False)
        if el >= 8.0 and 'neutral' not in self.D:
            self.D['neutral'] = True
            self.D['z_down'] = self.ship_loc()[2]
            self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, False)

    def end_lift(self):
        ss = [s for s in self.R['series'] if s['ph'] == 'lift']
        up = [s['VerticalSpeedMS'] for s in ss if s['t'] < self.p_t0 + 4.0]
        dn = [s['VerticalSpeedMS'] for s in ss if self.p_t0 + 4.0 <= s['t'] < self.p_t0 + 8.0]
        nt = [s for s in ss if s['t'] >= self.p_t0 + 9.0]
        z1 = self.ship_loc()[2]
        gain = (self.D.get('z_up', z1) - self.D['z0']) / 100.0
        loss = (self.D.get('z_up', z1) - self.D.get('z_down', z1)) / 100.0
        settle_vz = max(abs(s['VerticalSpeedMS']) for s in nt) if nt else None
        ok = gain > 2.0 and loss > 2.0 and max(up) > 1.0 and min(dn) < -1.0
        self.check('c_lift', 'PASS' if ok else 'FAIL', 'lift +1 4 s: +%.1f m (vz max %.2f m/s); lift -1 4 s: -%.1f m (vz min %.2f m/s); '
                   'neutral after: |vz| max %.2f m/s over the last 2 s, hold altitude %.1f m'
                   % (gain, max(up) if up else 0, loss, min(dn) if dn else 0, settle_vz or -1, nt[-1].get('HoldAltitudeM', 0) if nt else 0),
                   {'gain_m': gain, 'loss_m': loss, 'vz_up': up[::5], 'vz_down': dn[::5]})

    # ---- (d) throttle (+ (g) rig, (h) FX sampled in self.sample)
    def start_throttle(self):
        self.ship.debug_set_input(1.0, 0.0, 0.0, 0.0, False, False)
        self.D['fx0'] = self.fx_vals()

    def ph_throttle(self, el):
        if 5.0 < el < 5.1 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('throttle', 'below')

    def end_throttle(self):
        ss = [s for s in self.R['series'] if s['ph'] == 'throttle']
        curve = []
        for k in range(1, 11):
            c = [s for s in ss if s['t'] <= self.p_t0 + k]
            if c:
                curve.append(round(c[-1]['ForwardSpeedMS'], 2))
        top = max(s['ForwardSpeedMS'] for s in ss) if ss else 0
        alt = [s['AltitudeM'] for s in ss]
        pit = [s['PitchDeg'] for s in ss]
        ok = top > 10.0 and curve[-1] >= 0.9 * top
        self.check('d_throttle', 'PASS' if ok else 'FAIL', 'throttle 1 for 10 s: forward speed m/s at 1..10 s %s; top %.2f m/s; '
                   'altitude %.1f..%.1f m; pitch %.1f..%.1f deg' % (curve, top, min(alt), max(alt), min(pit), max(pit)),
                   {'curve': curve, 'top': top})
        self.eval_fx('throttle')

    # ---- (e) steer
    def start_steer(self):
        self.ship.debug_set_input(1.0, 1.0, 0.0, 0.0, False, False)
        self.D['yaw0'] = self.ship.get_actor_rotation().yaw
        self.D['yaw_prev'] = self.D['yaw0']
        self.D['yaw_sum'] = 0.0

    def ph_steer(self, el):
        y = self.ship.get_actor_rotation().yaw
        self.D['yaw_sum'] += wrap180(y - self.D['yaw_prev'])     # unwrapped heading change (it turns > 180 deg)
        self.D['yaw_prev'] = y
        if 4.0 < el < 4.1 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('turn', 'behind')
            self.capture('turn', 'player')

    def end_steer(self):
        ss = [s for s in self.R['series'] if s['ph'] == 'steer' and s['t'] >= self.p_t0 + 2.0]
        yr = [s['YawRateDegS'] for s in ss]
        rl = [s['RollDeg'] for s in ss]
        dyaw = self.D['yaw_sum']
        mean_yr = sum(yr) / len(yr) if yr else 0
        ok = mean_yr > 3.0 and dyaw > 10.0
        self.check('e_steer', 'PASS' if ok else 'FAIL', 'throttle 1 + steer +1 (D) 8 s: heading change %+.1f deg (+ = right / '
                   'clockwise seen from above), yaw rate (last 6 s) mean %+.2f deg/s (min %+.2f max %+.2f), roll %+.1f..%+.1f deg '
                   '(bank), speed %.1f m/s at the end' % (dyaw, mean_yr, min(yr), max(yr), min(rl), max(rl), ss[-1]['SpeedMS']),
                   {'dyaw': dyaw, 'yaw_rate_mean': mean_yr, 'roll_min': min(rl), 'roll_max': max(rl)})
        self.eval_rig()

    # ---- (f) boost + brake
    def start_boost(self):
        self.ship.debug_set_input(1.0, 0.0, 0.0, 0.0, True, False)
        t = self.tele()
        self.D['v0'], self.D['fuel0'] = t.get('ForwardSpeedMS'), t.get('BoostFuel')

    def ph_boost(self, el):
        if 2.0 < el < 2.1 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('boost', 'side')

    def end_boost(self):
        t = self.tele()
        ss = [s for s in self.R['series'] if s['ph'] == 'boost']
        self.R['boost'] = {'v0': self.D['v0'], 'v1': t.get('ForwardSpeedMS'), 'vmax': max(s['ForwardSpeedMS'] for s in ss),
                           'fuel0': self.D['fuel0'], 'fuel1': t.get('BoostFuel'), 'boost_shaped_max': max(s.get('Boost', 0) for s in ss)}
        self.eval_fx('boost')

    def start_brake(self):
        self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, True)
        self.D['v0'] = self.tele().get('ForwardSpeedMS')

    def end_brake(self):
        ss = [s for s in self.R['series'] if s['ph'] == 'brake']
        v = [s['ForwardSpeedMS'] for s in ss]
        t_half = next((s['t'] - self.p_t0 for s in ss if s['ForwardSpeedMS'] < 0.5 * self.D['v0']), None)
        b = self.R['boost']
        ok = b['vmax'] > (b['v0'] or 0) + 2.0 and (b['fuel1'] or 0) < (b['fuel0'] or 0) and v[-1] < 0.3 * self.D['v0']
        self.check('f_boost_brake', 'PASS' if ok else 'FAIL', 'boost 4 s: forward %.1f -> max %.1f m/s, fuel %.1f -> %.1f, shaped '
                   'Boost max %.2f; brake 4 s: %.1f -> %.1f m/s (half speed after %s s), bBraking %s'
                   % (b['v0'] or 0, b['vmax'], b['fuel0'] or 0, b['fuel1'] or 0, b['boost_shaped_max'], self.D['v0'], v[-1],
                      None if t_half is None else round(t_half, 2), any(s.get('bBraking') for s in ss)),
                   {'boost': b, 'brake': v[::5]})
        self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, False)

    # ---- (g) rig variables reach the bones
    def eval_rig(self):
        ss = [s for s in self.R['series'] if s.get('anim') and s.get('bones') and s['ph'] in ('throttle', 'steer', 'lift', 'hover')]
        pairs = {'TurbineYawDeg_L': 'TurbineYawDeg_L', 'RudderDeg': 'RudderDeg', 'NozzlePitchDeg_FL': 'NozzlePitchDeg_FL',
                 'NozzleRollDeg_FL': 'NozzleRollDeg_FL'}
        res = {}
        for a, b in pairs.items():
            d = [abs(s['anim'][a] - s['bones'][b]) for s in ss if s['anim'].get(a) is not None and b in s['bones']]
            rng = [s['anim'][a] for s in ss if s['anim'].get(a) is not None]
            res[a] = {'anim_range': [min(rng), max(rng)] if rng else None, 'max_abs_diff': max(d) if d else None,
                      'mean_abs_diff': sum(d) / len(d) if d else None}
        dw = [abs(wrap180(s['anim']['WheelAngleDeg'] - s['bones']['WheelAngleDeg_mod360'])) for s in ss
              if s['anim'].get('WheelAngleDeg') is not None and 'WheelAngleDeg_mod360' in s['bones']]
        res['WheelAngleDeg'] = {'anim_range': [min(s['anim']['WheelAngleDeg'] for s in ss), max(s['anim']['WheelAngleDeg'] for s in ss)],
                                'max_abs_diff': max(dw) if dw else None}
        dr = [abs(wrap180(s['anim']['RotorAngleDeg_L'] - s['bones']['RotorAngleDeg_L'])) for s in ss
              if s['anim'].get('RotorAngleDeg_L') is not None and 'RotorAngleDeg_L' in s['bones']]
        res['RotorAngleDeg_L'] = {'max_abs_diff': max(dr) if dr else None, 'n': len(dr)}
        fl = [abs(abs(s['anim']['NozzleFlareDeg_FL']) - s['bones']['NozzleFlareDeg_FL_abs']) for s in ss
              if s['anim'].get('NozzleFlareDeg_FL') is not None and 'NozzleFlareDeg_FL_abs' in s['bones']]
        res['NozzleFlareDeg_FL'] = {'anim_range': [min(s['anim']['NozzleFlareDeg_FL'] for s in ss), max(s['anim']['NozzleFlareDeg_FL'] for s in ss)],
                                    'max_abs_diff': max(fl) if fl else None}
        kin = [res['WheelAngleDeg']['max_abs_diff'], res['RotorAngleDeg_L']['max_abs_diff'], res['NozzleFlareDeg_FL']['max_abs_diff'],
               res['NozzlePitchDeg_FL']['max_abs_diff'], res['NozzleRollDeg_FL']['max_abs_diff']]
        moved = (res['WheelAngleDeg']['anim_range'][1] - res['WheelAngleDeg']['anim_range'][0] > 30.0 and
                 res['TurbineYawDeg_L']['anim_range'] and res['TurbineYawDeg_L']['anim_range'][1] - res['TurbineYawDeg_L']['anim_range'][0] > 3.0)
        ok = moved and all(x is not None and x < 1.0 for x in kin) and (res['TurbineYawDeg_L']['mean_abs_diff'] or 99) < 3.0
        self.check('g_rig_vars', 'PASS' if ok else 'FAIL', 'anim instance values vs the bones (kinematic bones must match; the '
                   'turbine and rudder lag/wobble on their Fx bodies): %s' % json.dumps(r(res, 2)), res)

    # ---- (h) Niagara params follow the thrust
    def eval_fx(self, ph):
        ss = [s for s in self.R['series'] if s.get('fx') and s['ph'] in ('hover', 'lift', 'throttle', 'steer', 'boost')]
        if not ss:
            return
        keys = sorted(set(k for s in ss for k in s['fx'] if k.endswith('Thrust') or k.endswith('Boost')))
        rng = {}
        for k in keys:
            vals = [s['fx'][k] for s in ss if s['fx'].get(k) is not None]
            rng[k] = [min(vals), max(vals)] if vals else None
        act = dict((k, all(s['fx'].get(k) for s in ss)) for k in ('ThrusterFX_FL.active', 'ThrusterFX_RR.active', 'TurbineFX_L.active'))
        thr = rng.get('ThrusterFX_FL.Thrust')
        fan = rng.get('TurbineFX_L.Thrust')
        bst = rng.get('TurbineFX_L.Boost') or rng.get('ThrusterFX_FL.Boost')
        ok = bool(thr and thr[1] - thr[0] > 0.05 and fan and fan[1] - fan[0] > 0.2 and all(act.values()))
        if ph == 'boost':
            ok = ok and bool(bst and bst[1] > 0.3)
        self.check('h_niagara' if ph == 'boost' else 'h_niagara_throttle', 'PASS' if ok else 'FAIL',
                   'Niagara user params over hover..%s (min, max): %s; components active %s' % (ph, json.dumps(r(rng, 3)), act),
                   {'ranges': rng, 'active': act})

    # ---- (j) damage + kill
    def start_damage(self):
        self.D['h0'] = self.tele().get('Health')
        self.D['hs'] = []

    def ph_damage(self, el):
        for i, at in enumerate((0.2, 1.0, 1.8)):
            if el >= at and 'd%d' % i not in self.D:
                self.D['d%d' % i] = True
                self.cmd('Aura.Airship.Damage 500')
            if el >= at + 0.5 and 'r%d' % i not in self.D:
                self.D['r%d' % i] = True
                self.D['hs'].append(self.tele().get('Health'))

    def end_damage(self):
        hs = self.D['hs']
        ok = len(hs) == 3 and abs((self.D['h0'] or 0) - 500 - hs[0]) < 1 and abs(hs[0] - 500 - hs[1]) < 1 and abs(hs[1] - 500 - hs[2]) < 1
        self.check('j1_damage', 'PASS' if ok else 'FAIL', 'Aura.Airship.Damage 500 x3: health %s -> %s (MaxHealth %s), alive %s'
                   % (self.D['h0'], hs, self.tele().get('MaxHealth'), not self.ship.is_airship_dead()), {'h0': self.D['h0'], 'hs': hs})

    def start_kill(self):
        self.ship.debug_clear_input()
        self.D['loc0'] = self.ship_loc()
        self.D['v0'] = v3(self.ship.get_velocity())
        self.D['track'] = []
        self.cmd('Aura.Airship.Kill')

    def wreck_offsets(self):
        out = {}
        for b in WREST:
            try:
                p, q = self.bone(b)
                rp, rq = self.rest[b]
                out[b] = [round(dist(p, rp), 1), round(qangle_axis(qmul(q, qinv(rq)))[0], 1)]
            except Exception:  # noqa: BLE001
                self.err('wreck_offsets')
        return out

    def ph_kill(self, el):
        if 'dead_t' not in self.D and self.ship.is_airship_dead():
            self.D['dead_t'] = el
        if 'pilot_t' not in self.D and self.pawn() == self.char:
            self.D['pilot_t'] = el
            self.D['pilot_attached'] = self.char.get_attach_parent_actor()
        if int(el * 5) != self.D.get('_k'):
            self.D['_k'] = int(el * 5)
            rec = {'t': round(el, 2), 'loc': r(self.ship_loc(), 0), 'vz': round(self.ship.get_velocity().z, 0),
                   'wreck': self.wreck_offsets(), 'anim_dead': self.anim_vals().get('bIsDead'), 'death_time': self.anim_vals().get('DeathTime')}
            self.D['track'].append(rec)
        z = self.ship_loc()[2]
        if 'ground_t' not in self.D and len(self.D['track']) > 5:
            vz = self.ship.get_velocity().z
            if z < -18000 and abs(vz) < 300:
                self.D['ground_t'] = el
                self.D['impact_vz'] = min(t['vz'] for t in self.D['track'])
        for at, kind in ((1.5, 'side'), (4.0, 'wreck')):
            if el >= at and 'cap%s' % at not in self.D:
                self.D['cap%s' % at] = True
                self.capture('death_%.1fs' % at, kind)
        gt = self.D.get('ground_t')
        if gt is not None and el >= gt + 2.5 and 'capg' not in self.D:
            self.D['capg'] = True
            self.capture('death_ground', 'wreck')
            self.capture('death_ground', 'side')

    def end_kill(self):
        tr = self.D['track']
        z = [t['loc'][2] for t in tr]
        ph = self.health(self.char)
        early = [t for t in tr if t['t'] <= 1.6]
        acc = None
        if len(early) >= 4:
            acc = (early[-1]['vz'] - early[1]['vz']) / max(1e-3, early[-1]['t'] - early[1]['t']) / 100.0
        last = tr[-1]['wreck'] if tr else {}
        moved = dict((b, v[0]) for b, v in last.items())
        brk = [b for b in ('Thruster_FL', 'Thruster_RR', 'Turbine_L', 'Turbine_R', 'Rudder', 'SearchLight_AftL', 'SearchLight_FwdC')
               if moved.get(b, 0) > 150.0]
        ok = (self.D.get('dead_t') is not None and self.D.get('pilot_t') is not None and self.D.get('ground_t') is not None
              and len(brk) >= 4 and acc is not None and acc < -7.0)
        self.check('j2_death', 'PASS' if ok else 'FAIL', 'Kill: dead after %s s; pilot back on foot after %s s (attached %s, '
                   'Health/Mana/Max %s); ship z %.0f -> min %.0f cm, vertical accel in the first 1.5 s %s m/s2 (forces off: '
                   '~ -9.8), on the ground plane after %s s (fastest fall %s cm/s); wreck parts moved from their rest place '
                   '(cm, deg) at the end: %s; broke off (> 1.5 m): %s; rig bIsDead %s DeathTime %s'
                   % (self.D.get('dead_t'), self.D.get('pilot_t'), self.D.get('pilot_attached'), ph, z[0] if z else 0,
                      min(z) if z else 0, None if acc is None else round(acc, 2), self.D.get('ground_t'), self.D.get('impact_vz'),
                      json.dumps(last), brk, tr[-1]['anim_dead'] if tr else None, tr[-1]['death_time'] if tr else None),
                   {'track': tr[::2], 'broke_off': brk})


def write_report(R):
    try:
        L = ['Airship PIE smoke test (%s), armed %s, game time %.1f s, wall %.0f s, reason: %s' % (
            R.get('version'), R.get('armed_utc'), R.get('game_t', 0), R.get('wall_s', 0), R.get('reason'))]
        L.append('setup: %s' % R.get('setup'))
        for k in sorted(R['checks']):
            c = R['checks'][k]
            L.append('%s %s: %s' % (c['status'], k, c['summary']))
        L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        for k, v in (R.get('log_scan') or {}).items():
            L.append('log %s: %d' % (k, v['count']))
            for s in v['sample'][:8]:
                L.append('    %s' % s[:300])
        L.append('captures: %s' % [s['file'] for s in R['shots']])
        L.append('')
        L.append('telemetry (1 Hz): t phase | loc | speed fwd lat | alt hold | vz | yawrate roll pitch | throttle steer lift boost brake | health')
        last = -1
        for s in R['series']:
            if int(s['t']) == last:
                continue
            last = int(s['t'])
            L.append('%6.1f %-8s | %s | %s %s %s | %s %s | %s | %s %s %s | %s %s %s %s %s | %s' % (
                s['t'], s['ph'], s.get('loc'), s.get('SpeedMS'), s.get('ForwardSpeedMS'), s.get('LateralSpeedMS'),
                s.get('AltitudeM'), s.get('HoldAltitudeM'), s.get('VerticalSpeedMS'), s.get('YawRateDegS'), s.get('RollDeg'),
                s.get('PitchDeg'), s.get('Throttle'), s.get('Steer'), s.get('Lift'), s.get('Boost'), s.get('bBraking'), s.get('Health')))
        with open(os.path.join(OUT, 'pie_smoke.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        with open(os.path.join(OUT, 'pie_smoke.txt'), 'w') as f:
            f.write('report failed: %s' % traceback.format_exc())


if 'AS30_RUN' in globals() and AS30_RUN is not None and AS30_RUN.phase not in ('finished',):
    print('FAIL: a run is active (phase %s): not armed again' % AS30_RUN.phase)
else:
    AS30_RUN = AsRun()
    if not AS30_RUN.arm():
        AS30_RUN.restore()
        AS30_RUN.remove_temp()
        AS30_RUN.phase = 'finished'
