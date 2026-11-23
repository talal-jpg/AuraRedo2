#!/usr/bin/env python3
"""as_50t_mock_pie.py - runs as_50_pie_controls.py end to end WITHOUT Unreal, for testing the harness itself.

A fake `unreal` module stands in for the editor: its "PIE world" is the bench (Docs/Airship/controls/sims/airship_sim.Sim
in place of the C++ ship, the bench scheme in place of the C++ scheme code), its Enhanced Input subsystem turns the
injections into the bench's RawInput, its console knows Aura.Airship.Board / Scheme / Telemetry. The harness runs
unchanged (state machine, board, scheme switch, start-pose resets, the protocol generator, captures as placeholder
PNGs, telemetry.json, metrics.json, compare.md, finish / restore / TEMP removal). It checks the plumbing, not the C++.
With a fresh bench Sim per scheme apply, the metrics come out close to the sims' JSONs (not exact: the start-pose
reset adds hover time, the wind phase differs). --listen: the listen-server pass (two worlds; the client's copy of the
ship shows the bench's 100 ms client view; player index 1 boards), which fills the lat100 keys.

    python3 Docs/Airship/scripts/ue/as_50t_mock_pie.py [--schemes 0,2] [--runs m1_m2,m11_precise] [--out DIR] [--post]
                                                       [--listen] [--keep]   (--keep: do not wipe DIR's results first)
                                                       [--break scheme|inject]  (fault injection: the C++ ignores
                                                       Aura.Airship.Scheme / Enhanced Input does nothing)

Output: DIR (default /tmp/claude-1000/as50_mock)/Saved/Airship/controls/. One bench process, ~10-20 s per scheme.
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import types
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import as_50_protocol as P  # noqa: E402

P.load_bench()
A = P.B.A
DT = A.DT
GROUND = -19950.0
MAP_PATH = '/Game/Assets/MyShip/Drivable/Maps/L_AirshipTest'


# ------------------------------------------------------------------------------------------------- value types
class Vector(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o):
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s):
        return Vector(self.x * s, self.y * s, self.z * s)

    def __repr__(self):
        return 'Vector(%.1f, %.1f, %.1f)' % (self.x, self.y, self.z)


class Rotator(object):
    def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
        self.roll, self.pitch, self.yaw = float(roll), float(pitch), float(yaw)


class EnumVal(object):
    def __init__(self, name):
        self.name = name

    def __eq__(self, o):
        return isinstance(o, EnumVal) and o.name == self.name

    def __hash__(self):
        return hash(self.name)


def enum(*names):
    return types.SimpleNamespace(**dict((n, EnumVal(n)) for n in names))


class Cls(object):
    def __init__(self, name):
        self._name = name

    def get_name(self):
        return self._name


class Obj(object):
    _n = 0

    def __init__(self, cls='Object', name=None, **props):
        Obj._n += 1
        self._cls = Cls(cls)
        self._name = name or '%s_%d' % (cls, Obj._n)
        self.props = dict(props)
        self.destroyed = False
        self.label = self._name

    def get_name(self):
        return self._name

    def get_class(self):
        return self._cls

    def get_path_name(self):
        return '/Mock/' + self._name

    def get_editor_property(self, n):
        if n not in self.props:
            raise AttributeError(n)
        return self.props[n]

    def set_editor_property(self, n, v, *a):
        self.props[n] = v

    def get_actor_label(self):
        return self.label

    def set_actor_label(self, l):
        self.label = l


# ------------------------------------------------------------------------------------------------- the mock editor
class Mock(object):
    def __init__(self, saved, listen=False):
        self.saved = saved
        self.listen = listen
        self.world_c = None
        os.makedirs(os.path.join(saved, 'Logs'), exist_ok=True)
        self.log_path = os.path.join(saved, 'Logs', 'Aura.log')
        open(self.log_path, 'w').close()
        self.callbacks = {}
        self.in_pie = False
        self.pie_pending = 0
        self.end_pending = 0
        self.time = 0.0
        self.frames = 0
        self.level = []
        self.editor_world = Obj('World', 'L_AirshipTest')
        self.editor_world.get_path_name = lambda: MAP_PATH + '.L_AirshipTest'
        self.engine = Obj('UnrealEdEngine', bUseFixedFrameRate=False, FixedFrameRate=30.0)
        self.play = Obj('LevelEditorPlaySettings', PlayNetMode='PIE_Standalone', PlayNumberOfClients=1, RunUnderOneProcess=True)
        self.burrower = Obj('BurrowerSettings', bEnabled=True)
        self.world = None
        self.sim = None
        self.scheme_id = 0
        self.pilot = False
        self.injected = {}
        self.debug = None
        self.pc_rot = [-12.0, 0.0]
        self.pc_dirty = False

    def log(self, msg):
        with open(self.log_path, 'a') as f:
            f.write('[%s][%4d]LogAirship: %s\n' % (time.strftime('%Y.%m.%d-%H.%M.%S'), self.frames % 1000, msg))

    # ---- PIE lifecycle
    def begin_play(self):
        self.pie_pending = 3

    def end_play(self):
        self.end_pending = 2

    def start_pie(self):
        self.world = Obj('World', 'UEDPIE_0_L_AirshipTest')
        self.world.get_path_name = lambda: '/Game/Assets/MyShip/Drivable/Maps/UEDPIE_0_L_AirshipTest.L_AirshipTest'
        if self.listen:
            self.world_c = Obj('World', 'UEDPIE_1_L_AirshipTest')
            self.world_c.get_path_name = lambda: '/Game/Assets/MyShip/Drivable/Maps/UEDPIE_1_L_AirshipTest.L_AirshipTest'
        self.time = 0.0
        # the C++ default scheme (AAirshipPawn::ControlScheme) is Point & Fly since the 2026-11-23 polish
        self.scheme_id = 3
        self.sim = self.new_sim(3, (0.0, 25.0, (1600.0 - GROUND) / 100.0), 0.0)
        self.pilot = False
        self.in_pie = True
        self.log('PIE started (mock)')

    def ground(self, x, y):
        return GROUND

    def targets(self):
        out = []
        for a in self.level:
            if a.label == 'TEMP_AS50_Target' and not a.destroyed:
                out.append(((a.loc.x, a.loc.y, a.loc.z), 50.0 * a.scale.x))
        return out

    def new_sim(self, sid, pos_agl, yaw, vel=(0.0, 0.0, 0.0)):
        key = P.SCHEMES[sid][0]
        sim = A.Sim(A.load_scheme(key), latency_ms=100.0 if self.listen else 0.0, alt_agl=pos_agl[2], pos_m=(pos_agl[0], pos_agl[1]),
                    yaw_deg=yaw, seed=1, ground_fn=self.ground)
        sim.body.v = tuple(vel)
        sim.aim_targets = self.targets()
        return sim

    def apply_scheme(self, sid):
        """The C++ ApplyControlScheme: a preset and fresh scheme state. Mock: a new bench Sim of that scheme at the same pose
        and velocity (fresh hold, fuel, shaped controls)."""
        old = self.sim
        loc = old.body.actor_loc()
        pit, yaw, roll = A.quat2rot(old.body.q)
        v = old.body.v
        sim = self.new_sim(sid, (loc[0] / 100.0, loc[1] / 100.0, (loc[2] - GROUND) / 100.0), yaw, v)
        sim.set_state(yaw_deg=yaw, pitch_deg=pit, roll_deg=roll)
        sim.body.w = old.body.w
        sim.cam.control_yaw, sim.cam.control_pitch = self.pc_rot[1], self.pc_rot[0]
        self.sim = sim
        self.scheme_id = sid
        self.log('Aura.Airship.Scheme: BP_AirshipPawn_C_0 -> %s (%d)' % (P.SCHEMES[sid][1], sid))

    def console(self, c):
        parts = c.split()
        if BREAK == 'scheme' and parts and parts[0] == 'Aura.Airship.Scheme' and len(parts) > 1 and parts[1] != 'check':
            self.log('Aura.Airship.Scheme: ignored (mock --break scheme)')
            return
        if not parts:
            return
        if parts[0] == 'Aura.Airship.Board':
            self.pilot = True
            self.log('Aura.Airship.Board: boarded')
        elif parts[0] == 'Aura.Airship.Scheme':
            if len(parts) == 1:
                self.log('Aura.Airship.Scheme: BP_AirshipPawn_C_0: %s (%d), active %d' % (P.SCHEMES[self.scheme_id][1], self.scheme_id, self.scheme_id))
            elif parts[1] == 'check':
                self.log('Aura.Airship.Scheme check: 0 differences from the archetype (mock)')
            else:
                self.apply_scheme(int(parts[1]))
        elif parts[0].startswith('Net'):
            self.log('%s (mock: no network, the bench lags the client by its latency_ms)' % c)
        elif parts[0] == 'Aura.Airship.Telemetry':
            self.log('Aura.Airship.Telemetry: inertia (6.86, 1.10, 6.57) e10 kg cm2 MassSpace (mock)')

    # ---- one engine frame: the pilot's inputs from the last post-tick go into the bench step
    def engine_tick(self):
        if self.pie_pending:
            self.pie_pending -= 1
            if self.pie_pending == 0:
                self.start_pie()
            return
        if self.end_pending:
            self.end_pending -= 1
            if self.end_pending == 0:
                self.in_pie = False
                self.world = self.world_c = None
            return
        if not self.in_pie:
            return
        inj, self.injected = self.injected, {}
        raw = A.RawInput()
        if self.pilot:
            g = lambda n: inj[n].x if n in inj else 0.0  # noqa: E731
            raw.throttle, raw.steer, raw.lift, raw.strafe = g('IA_AirshipThrottle'), g('IA_AirshipSteer'), g('IA_AirshipLift'), g('IA_AirshipStrafe')
            raw.boost, raw.brake, raw.aim = 'IA_AirshipBoost' in inj, 'IA_AirshipBrake' in inj, 'IA_AirshipAim' in inj
            raw.fire, raw.look = 'IA_AirshipFire' in inj, 'IA_AirshipLook' in inj
            raw.zoom = g('IA_AirshipZoom')
            if self.pc_dirty:
                raw.cam_pitch, raw.cam_yaw = self.pc_rot
            if self.debug is not None:
                d = self.debug
                raw = A.RawInput(throttle=d[0], steer=d[1], lift=d[2], strafe=d[3], boost=d[4], brake=d[5])
        self.pc_dirty = False
        self.sim.step(raw)
        self.pc_rot = [self.sim.cam.control_pitch, self.sim.cam.control_yaw]
        self.frames += 1
        self.time = self.frames * DT


M = None


# ------------------------------------------------------------------------------------------------- mock actors
class Hull(Obj):
    def set_physics_linear_velocity(self, v, add=False, bone=None):
        M.sim.body.v = (v.x, v.y, v.z)

    def set_physics_angular_velocity_in_degrees(self, v, add=False, bone=None):
        M.sim.body.w = (math.radians(v.x), math.radians(v.y), math.radians(v.z))


class Anim(Obj):
    def get_editor_property(self, n):
        s = M.sim
        c = s.pilot_fm.cosmetic or {}
        g = c.get('PodGimbal') or [(0.0, 0.0)] * 4
        m = {'WheelAngleDeg': s.anim.wheel, 'TurbineYawDeg_L': s.anim.turbine_yaw, 'TurbineYawDeg_R': s.anim.turbine_yaw,
             'NozzlePitchDeg_FL': g[0][0], 'NozzlePitchDeg_RR': g[3][0], 'RudderDeg': 0.0, 'ThrustAlpha_FL': (c.get('PodThrustAlpha') or [0])[0],
             'NozzleFlareDeg_FL': 0.0}
        return m[n]


class Mesh(Obj):
    def get_anim_instance(self):
        return self.props['anim']


class Tele(object):
    def __init__(self, d):
        self.d = d

    def export_text(self):
        def f(v):
            if isinstance(v, bool):
                return 'True' if v else 'False'
            if isinstance(v, int):
                return '%d' % v
            return '%.6f' % v
        return '(' + ','.join('%s=%s' % (k, f(v)) for k, v in self.d.items()) + ')'


class Ship(Obj):
    def __init__(self):
        Obj.__init__(self, 'BP_AirshipPawn_C', 'BP_AirshipPawn_C_0')
        self.props['HullCollision'] = Hull('StaticMeshComponent')
        self.props['Mesh'] = Mesh('SkeletalMeshComponent', anim=Anim('ABP_Airship_C'))

    def get_flight_telemetry(self):
        t = M.sim.tele()
        d = {}
        for k in P.BASE_FIELDS + P.CONTRACT_FIELDS + ('DriftDir', 'TurboAlpha', 'TurboChain'):
            if k in t:
                v = t[k]
                d[k] = int(v) if k in ('Scheme', 'DriftDir', 'TurboChain') else (bool(v) if isinstance(v, bool) else float(v))
        d.update(Health=2000.0, MaxHealth=2000.0, bHasPilot=M.pilot, bIsDead=False, DriftTier=0, bGunDeck=False)   # bGunLock left out
        return Tele(d)

    def get_actor_location(self):
        return Vector(*M.sim.body.actor_loc())

    def get_velocity(self):
        return Vector(*M.sim.body.v)

    def get_actor_forward_vector(self):
        return Vector(*A.qrot(M.sim.body.q, (1.0, 0.0, 0.0)))

    def get_actor_right_vector(self):
        return Vector(*A.qrot(M.sim.body.q, (0.0, 1.0, 0.0)))

    def set_actor_location_and_rotation(self, v, rot, sweep, teleport):
        M.sim.set_state(pos_m=(v.x / 100.0, v.y / 100.0), alt_m=v.z / 100.0, yaw_deg=rot.yaw, pitch_deg=rot.pitch, roll_deg=rot.roll)
        M.sim.aim_targets = M.targets()

    def get_pilot(self):
        return CHAR if M.pilot else None

    def has_pilot(self):
        return M.pilot

    def get_aim_side(self):
        return EnumVal('PORT' if M.sim.aim_side == 'port' else 'STARBOARD')

    def get_control_scheme(self):
        return EnumVal(P.SCHEMES[M.scheme_id][2])

    def set_control_scheme(self, e):
        if BREAK != 'scheme':
            M.apply_scheme([k for k, v in P.SCHEMES.items() if v[2] == e.name][0])

    def debug_set_input(self, *a):
        M.debug = a

    def debug_clear_input(self):
        M.debug = None

    def get_local_role(self):
        return EnumVal('ROLE_AUTHORITY')


class ShipC(Ship):
    """The client's copy (listen mode): the bench's lagged pilot view, the pilot's own shaped controls."""

    def __init__(self):
        Ship.__init__(self)

    def view(self):
        return M.sim.pilot_view()

    def get_flight_telemetry(self):
        d = Ship.get_flight_telemetry(self).d
        v = self.view()
        for k in P.BASE_FIELDS + P.CONTRACT_FIELDS:
            if k in v and k in d:
                d[k] = int(v[k]) if k == 'Scheme' else (bool(v[k]) if isinstance(v[k], bool) else float(v[k]))
        fm = M.sim.pilot_fm
        d.update(Throttle=fm.sh_throttle, Steer=fm.sh_steer, Lift=fm.sh_lift, Strafe=fm.sh_strafe, Boost=fm.sh_boost,
                 bBraking=bool(fm.b_brake), bDrifting=bool(fm.b_drifting))
        if hasattr(fm, 'sky_drift_dir'):
            d['DriftDir'] = int(fm.sky_drift_dir)
        if hasattr(fm, 'order'):
            d['ThrottleOrder'] = {-1: -1.0, 0: 0.0, 1: 1.0 / 3.0, 2: 2.0 / 3.0, 3: 1.0}.get(fm.order, 0.0)
        return Tele(d)

    def get_actor_location(self):
        return Vector(*self.view()['ActorLocCm'])

    def get_velocity(self):
        return Vector(*self.view()['VelCm'])

    def get_local_role(self):
        return EnumVal('ROLE_AUTONOMOUS_PROXY')


class PC(Obj):
    def get_controlled_pawn(self):
        if self.props.get('host'):
            return CHAR_H
        return (SHIP_C if M.listen else SHIP) if M.pilot else CHAR

    def get_control_rotation(self):
        return Rotator(0.0, M.pc_rot[0] % 360.0, M.pc_rot[1])

    def set_control_rotation(self, r):
        p = r.pitch if r.pitch <= 180.0 else r.pitch - 360.0
        M.pc_rot = [p, r.yaw]
        M.pc_dirty = True

    def is_local_controller(self):
        return not self.props.get('remote')


class PCM(Obj):
    def get_camera_location(self):
        s = M.sim
        return Vector(*[c * 100.0 for c in s.camera_location_m(s.tele())])

    def get_camera_rotation(self):
        return Rotator(0.0, M.sim.cam.view_pitch, M.sim.cam.view_yaw)

    def get_fov_angle(self):
        return 85.0


class LP(Obj):
    def get_world(self):
        return M.world_c if M.listen else M.world


class Sub(Obj):
    def get_outer(self):
        return LPI

    def inject_input_vector_for_action(self, action, v, mods, trigs):
        if BREAK != 'inject':
            M.injected[action.get_name()] = v


class LevelActor(Obj):
    def __init__(self, cls, loc, rot=None, mesh=None):
        Obj.__init__(self, cls)
        self.loc, self.rot, self.scale = loc, rot or Rotator(), Vector(1.0, 1.0, 1.0)
        if cls == 'SceneCapture2D':
            self.capture_component2d = Obj('SceneCaptureComponent2D')
            self.capture_component2d.capture_scene = lambda: None
        if cls == 'StaticMeshActor':
            c = Obj('StaticMeshComponent')
            c.set_collision_profile_name = lambda n: c.props.__setitem__('profile', n)
            c.set_material = lambda i, m: c.props.__setitem__('material', m)
            self.static_mesh_component = c

    def set_actor_scale3d(self, s):
        self.scale = s

    def set_actor_location_and_rotation(self, v, rot, sweep, teleport):
        self.loc, self.rot = v, rot


def tiny_png(path, w=16, h=16, shade=90):
    raw = b''.join(b'\x00' + bytes([shade, shade + 20, shade + 60]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


SHIP = CHAR = LPI = SUB = PCI = PCMI = None
BREAK = None
SHIP_C = CHAR_H = HPC = RPC = None


def build_unreal(saved, listen=False):
    global M, SHIP, CHAR, LPI, SUB, PCI, PCMI, SHIP_C, CHAR_H, HPC, RPC
    M = Mock(saved, listen)
    SHIP, CHAR = Ship(), Obj('BP_MyCharMech_C', 'BP_MyCharMech_C_1')
    SHIP_C, CHAR_H = ShipC(), Obj('BP_MyCharMech_C', 'BP_MyCharMech_C_0')
    HPC, RPC = PC('PlayerController', host=True), PC('PlayerController', remote=True)
    LPI, SUB, PCI, PCMI = LP('LocalPlayer'), Sub('EnhancedInputLocalPlayerSubsystem'), PC('PlayerController'), PCM('PlayerCameraManager')
    u = types.ModuleType('unreal')
    LES, EAS, UES = Cls('LevelEditorSubsystem'), Cls('EditorActorSubsystem'), Cls('UnrealEditorSubsystem')
    u.LevelEditorSubsystem, u.EditorActorSubsystem, u.UnrealEditorSubsystem = LES, EAS, UES
    u.SceneCapture2D, u.StaticMeshActor, u.PlayerController = Cls('SceneCapture2D'), Cls('StaticMeshActor'), Cls('PlayerController')
    u.EnhancedInputLocalPlayerSubsystem = Cls('EnhancedInputLocalPlayerSubsystem')
    u.Vector, u.Rotator = Vector, Rotator
    u.PropertyAccessChangeNotifyMode = enum('NEVER')
    u.ComponentMobility = enum('MOVABLE', 'STATIC')
    u.TextureRenderTargetFormat = enum('RTF_RGBA8')
    u.SceneCaptureSource = enum('SCS_FINAL_COLOR_LDR')
    u.VisibilityBasedAnimTickOption = enum('ALWAYS_TICK_POSE_AND_REFRESH_BONES')
    u.AirshipControlScheme = enum('CLASSIC', 'GALLEON', 'SKY_RACER', 'POINT_FLY')
    u.log = u.log_warning = lambda m: None
    u.Paths = types.SimpleNamespace(project_saved_dir=lambda: saved + '/', project_dir=lambda: os.path.dirname(saved) + '/')
    u.ToolsetLibrary = types.SimpleNamespace(
        get_object_properties=lambda o, names: json.dumps(dict((n, o.props.get(n)) for n in names)),
        set_object_properties=lambda o, js: o.props.update(json.loads(js)) or True)

    def find_object(outer, path):
        return M.engine if 'UnrealEdEngine' in path else None
    u.find_object = find_object
    u.load_class = lambda outer, path: Cls(path.split('.')[-1])
    u.load_asset = lambda path: Obj('Asset', path.split('/')[-1])

    def get_default_object(cls):
        n = cls.get_name()
        return M.play if 'LevelEditorPlaySettings' in n else (M.burrower if 'BurrowerSettings' in n else Obj('CDO'))
    u.get_default_object = get_default_object

    class _LES(object):
        def is_in_play_in_editor(self):
            return M.in_pie or bool(M.end_pending)

        def editor_request_begin_play(self):
            M.begin_play()

        def editor_request_end_play(self):
            M.end_play()

    class _EAS(object):
        def get_all_level_actors(self):
            return [a for a in M.level if not a.destroyed]

        def spawn_actor_from_class(self, cls, loc, rot=None):
            a = LevelActor(cls.get_name(), loc, rot)
            M.level.append(a)
            return a

        def spawn_actor_from_object(self, obj, loc, rot=None):
            a = LevelActor('StaticMeshActor', loc, rot, obj)
            M.level.append(a)
            return a

        def destroy_actor(self, a):
            a.destroyed = True
            return True

    class _UES(object):
        def get_editor_world(self):
            return M.editor_world
    subs = {'LevelEditorSubsystem': _LES(), 'EditorActorSubsystem': _EAS(), 'UnrealEditorSubsystem': _UES()}
    u.get_editor_subsystem = lambda cls: subs[cls.get_name()]
    u.register_slate_post_tick_callback = lambda fn: M.callbacks.setdefault(id(fn), fn) and id(fn)
    u.unregister_slate_post_tick_callback = lambda h: M.callbacks.pop(h, None)
    u.EditorLevelLibrary = types.SimpleNamespace(
        get_pie_worlds=lambda inc: ([M.world] + ([M.world_c] if M.world_c else [])) if (M.in_pie and M.world) else [])
    u.SystemLibrary = types.SimpleNamespace(
        is_valid=lambda a: a is not None and not getattr(a, 'destroyed', False), is_standalone=lambda w: not M.listen,
        is_server=lambda w: w is M.world, execute_console_command=lambda w, c: M.console(c))

    def all_of_class(w, cls):
        n = cls.get_name()
        if 'BP_AirshipPawn' in n:
            return [SHIP_C] if (M.listen and w is M.world_c) else [SHIP]
        if 'AirshipCannonball' in n:
            return [Obj('AirshipCannonball', 'AirshipCannonball_%d' % i) for i in range(len(M.sim.cannon_shots))]
        if n in ('SceneCapture2D', 'StaticMeshActor'):
            return [a for a in M.level if a.get_class().get_name() == n and not a.destroyed]
        if n == 'PlayerController':
            return [HPC, RPC] if M.listen else [PCI]
        return []
    u.GameplayStatics = types.SimpleNamespace(
        get_time_seconds=lambda w: M.time, get_all_actors_of_class=all_of_class,
        get_player_controller=lambda w, i: (HPC if (M.listen and w is M.world) else PCI),
        get_player_camera_manager=lambda w, i: PCMI)
    u.ObjectIterator = lambda cls: iter([SUB])

    def look_at(a, b):
        d = (b.x - a.x, b.y - a.y, b.z - a.z)
        return Rotator(0.0, math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), math.degrees(math.atan2(d[1], d[0])))
    u.MathLibrary = types.SimpleNamespace(find_look_at_rotation=look_at)

    def export_rt(w, rt, folder, name):
        os.makedirs(folder, exist_ok=True)
        tiny_png(os.path.join(folder, name), shade=40 + (M.frames % 120))
    u.RenderingLibrary = types.SimpleNamespace(create_render_target2d=lambda w, x, y, f: Obj('TextureRenderTarget2D'),
                                               export_render_target=export_rt)
    return u


def main(argv):
    out, schemes, runs, post, listen, keep = '/tmp/claude-1000/as50_mock', [0], None, False, False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--out':
            out = argv[i + 1]
            i += 1
        elif a == '--schemes':
            schemes = [int(x) for x in argv[i + 1].split(',')]
            i += 1
        elif a == '--runs':
            runs = argv[i + 1].split(',')
            i += 1
        elif a == '--post':
            post = True
        elif a == '--listen':
            listen = True
        elif a == '--keep':
            keep = True
        elif a == '--break':
            global BREAK
            BREAK = argv[i + 1]
            i += 1
        i += 1
    saved = os.path.join(out, 'Saved')
    if os.path.isdir(os.path.join(saved, 'Airship', 'controls')) and not keep:
        shutil.rmtree(os.path.join(saved, 'Airship', 'controls'))
    u = build_unreal(saved, listen)
    sys.modules['unreal'] = u
    ns = {'unreal': u, '__name__': '__pt__'}
    ns['AS50_CFG'] = {'schemes': schemes, 'runs': runs, 'auto_post': False, 'capture_every': 4, 'min_free_gb': 0.2,
                      'net': 'listen' if listen else 'standalone'}
    harness = os.path.join(HERE, 'as_50_pie_controls.py')
    t0 = time.time()
    exec(compile(open(harness).read(), harness, 'exec'), ns)
    run = ns['AS50_RUN']
    n = 0
    while run.phase != 'finished' and n < 400000:
        M.engine_tick()
        for cb in list(M.callbacks.values()):
            cb(DT)
        n += 1
    print('mock PIE: %d engine frames, %.1f s wall, phase %s, reason %s' % (n, time.time() - t0, run.phase, run.R.get('reason')))
    print('errors: %s' % dict((k, v['n']) for k, v in run.R['errors'].items()))
    for k, v in run.R['errors'].items():
        print('--- %s\n%s' % (k, v['last'][-1200:]))
    left = [a.label for a in M.level if not a.destroyed]
    print('TEMP actors left in the level: %d; engine fixed fps restored %s; play settings %s; burrower %s' % (
        len(left), M.engine.props, M.play.props, M.burrower.props))
    ctrl = os.path.join(saved, 'Airship', 'controls')
    for k in schemes:
        key = P.SCHEMES[k][0]
        mp = os.path.join(ctrl, key, 'metrics.json')
        if os.path.exists(mp):
            m = json.load(open(mp))
            ref = P.load_sim_metrics(key) or {}
            print('%s: runs %s' % (key, dict((n, r.get('status')) for n, r in m['meta']['runs'].items())))
            for mm in ('M1', 'M2', 'M4', 'M5', 'M7', 'M9'):
                print('  %s pie %s' % (mm, json.dumps(m.get(mm))))
                print('  %s sim %s' % (mm, json.dumps(ref.get(mm))))
            print('  M11 precise lat0 pie %s' % json.dumps(m['M11']['precise']['lat0']))
            print('  M11 precise lat0 sim %s' % json.dumps(ref.get('M11', {}).get('precise', {}).get('lat0')))
            print('  M12 precise lat0 pie %s' % json.dumps(m['M12']['precise']['lat0']))
            print('  M12 precise lat0 sim %s' % json.dumps(ref.get('M12', {}).get('precise', {}).get('lat0')))
            if listen:
                print('  listen pass runs %s' % dict((n, r.get('status')) for n, r in m['meta']['listen_pass']['runs'].items()))
                for mm in ('M10',):
                    print('  %s pie %s' % (mm, json.dumps(m.get(mm))))
                    print('  %s sim %s' % (mm, json.dumps(ref.get(mm))))
                print('  M11 sloppy lat100 pie %s' % json.dumps(m['M11']['sloppy']['lat100']))
                print('  M11 sloppy lat100 sim %s' % json.dumps(ref.get('M11', {}).get('sloppy', {}).get('lat100')))
                print('  M12 precise lat100 pie %s' % json.dumps(m['M12']['precise']['lat100']))
                print('  M12 precise lat100 sim %s' % json.dumps(ref.get('M12', {}).get('precise', {}).get('lat100')))
    print('outputs: %s' % sorted(os.listdir(ctrl)))
    if post:
        subprocess.run([sys.executable, '-I', os.path.join(HERE, '..', 'harness', 'as_50_post.py'), '--root', ctrl])


if __name__ == '__main__':
    main(sys.argv[1:])
