# as_50_pie_controls.py - PIE test of the airship control schemes (Classic, Galleon, Sky Racer, Point & Fly) for the
# judging of the control iterations. L_AirshipTest, fixed 30 fps game time, Standalone (1 player) by default.
#
# RUN (clone editor open on /Game/Assets/MyShip/Drivable/Maps/L_AirshipTest with the Python inbox, no PIE running,
# the C++ with the control-scheme CONTRACT built; keep the editor on the visible i3 workspace or it runs ~10x slower):
#   Docs/Airship/scripts/harness/inbox.sh 50 Docs/Airship/scripts/ue/as_50_pie_controls.py 120
# It arms a frame-by-frame state machine (Slate post-tick callback, as as_30 / as_43 / as_45), starts PIE and returns
# at once. Poll:  cat Saved/Airship/controls/status.txt   (rewritten every 2 s), or
#   Docs/Airship/scripts/harness/inbox.sh 50s Docs/Airship/scripts/ue/as_50s_status.py 30
# Stop early (ends its own PIE, restores the settings, removes the TEMP actors, writes what it has):
#   Docs/Airship/scripts/harness/inbox.sh 50x Docs/Airship/scripts/ue/as_50x_stop.py 30
# Options: an inbox script that sets AS50_CFG first, e.g.
#   AS50_CFG = {'schemes': [2, 3], 'capture': False}
#   exec(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_50_pie_controls.py').read())
# keys: schemes [0, 1, 2, 3] | net 'standalone' (lat0 values) or 'listen' (second pass, Play As Listen Server with 2
# players set in memory: the client pilots with Net PktLag 100 each way and fills the lat100 values of M10-M12) |
# runs None (a list of run names, e.g. ['m1_m2', 'm11_precise']) | capture True | capture_every 4 | chase_res
# (1280, 720) | still_res (1920, 1080) | capture_skills ('precise',) | xgrab False (HUD grabs: run
# harness/xgrab_loop.sh Saved/Airship/controls/xgrab beside it) | classic_crosscheck False (a DebugSetInput run of
# Classic's M1 / M4) | auto_post True (as_50_post.py after PIE: mp4, contact sheets, compare.md) | require_scheme True |
# sloppy_repeats 3 (the sloppy course 3 times: one run moves by 1-2 gates with the wind phase alone).
#
# DURATION (game time = wall time when the editor holds 30 fps): about 11 min of game time per scheme (17 runs: probe,
# M1-M10, the gate course 1 + 3 times, the broadside orbit twice) + ~1 min of captures and writes: ~45-50 min for the
# four schemes (sloppy_repeats 1: ~38 min). Listen pass ~8 min per scheme. The post step (ffmpeg / montage) adds 2-4
# min after PIE. Full protocol: Docs/Airship/controls/TEST_PROTOCOL.md. Offline checks without Unreal:
#   python3 Docs/Airship/scripts/ue/as_50_protocol.py --selftest <scheme> [--lat100]   (protocol = bench, exact)
#   python3 Docs/Airship/scripts/ue/as_50t_mock_pie.py --schemes 0,1,2,3 [--post]       (this file, mock editor)
#
# WHAT IT DOES per scheme id: board the ship once (Aura.Airship.Board), "Aura.Airship.Scheme <id>" (console, server),
# confirm it (GetControlScheme + telemetry Scheme), log "Aura.Airship.Telemetry" (the inertia line), then the runs of
# as_50_protocol.py: an Enhanced Input probe, M1-M10 (open-loop maneuvers through the scheme's own controls) and the
# gate course M11 / broadside M12 flown by the bench's precise and sloppy-human bots. Every run starts at rest from a
# teleport (scheme re-applied, altitude hold re-latched by a brake tap, camera behind the ship). Inputs: Enhanced Input
# injection on the pilot's local player (raw axis / button values) + the PlayerController's control rotation; never
# DebugSetInput (except the optional Classic cross-check). Same metric code as Docs/Airship/controls/sims/metrics.py /
# course.py (as_50_protocol.py; its --selftest checks it against the bench without Unreal).
# In memory only, restored at the end: UnrealEdEngine fixed frame rate 30, LevelEditorPlaySettings (Standalone 1 or
# Listen 2), BurrowerSettings.bEnabled False, Net PktLag (listen). TEMP_AS50_* actors in the editor level (2 scene
# captures, 11 course gates = 44 meshes, the M12 target sphere), removed after PIE; the map is never saved (it shows
# as modified, its content is unchanged). The user's own Play is never stopped.
#
# OUTPUTS (Saved/Airship/controls/): status.txt, as50_log.txt, as50_result.json, compare.md (every metric x scheme,
# PIE (sim)); per scheme <key>/ (classic, galleon, skyracer, pointfly): metrics.json (meta + M1..M12, the sims' keys,
# meta.source 'pie'), telemetry.json (every frame of every run: telemetry incl. the CONTRACT fields, raw inputs,
# camera, rig cosmetics), chase/chase_NNNNN.png + frames.json (the precise course run, the pilot's camera, every 4th
# frame), stills/ (start, slalom, hairpin apex, climb, drift/boost moment, finish, broadside: pilot view + wide view);
# after as_50_post.py: <key>/course_<key>.mp4, contact_<key>.png, stills_<key>.png, compare_course_2x2.mp4.
import json, math, os, shutil, subprocess, sys, time, traceback, importlib  # unreal = inbox namespace

AS50_VERSION = 'as_50_pie_controls 2026-11-23'
AS50_W = '/mnt/new_partition/UnrealProjects/_AirshipWork'
AS50_UE = os.path.join(AS50_W, 'Docs', 'Airship', 'scripts', 'ue')
_as50_src = open(os.path.join(AS50_UE, 'as_30_pie_smoke.py')).read()
exec(compile(_as50_src[:_as50_src.index('\nclass AsRun')], os.path.join(AS50_UE, 'as_30_pie_smoke.py'), 'exec'), globals())
# ^ v3, r, wrap180, dist, tl_get, tl_set, gp, valid, find_log, parse_struct, OUT, MAP_NAME, SHIP_CLS, BALL_CLS, FIXED_FPS

if AS50_UE not in sys.path:
    sys.path.insert(0, AS50_UE)
import as_50_protocol as AS50P  # noqa: E402
AS50P = importlib.reload(AS50P)
AS50P.load_bench(reload=True)

AS50_CTRL = os.path.join(OUT, 'controls')
AS50_IA = '/Game/Assets/MyShip/Drivable/Input/'
AS50_ACTIONS = ('IA_AirshipThrottle', 'IA_AirshipSteer', 'IA_AirshipLift', 'IA_AirshipStrafe', 'IA_AirshipBoost',
                'IA_AirshipBrake', 'IA_AirshipFire', 'IA_AirshipAim', 'IA_AirshipLook', 'IA_AirshipZoom', 'IA_AirshipExit')
AS50_TEMP = 'TEMP_AS50_'
AS50_GROUND_TOP = -19950.0                      # AS_Ground top (cm): as_22_test_map.py, as_43
# Test areas (cm, world): far from the obstacles (they sit 13-60 m above z 0 at x 350..1500, y -300..450 m), over the
# 4 x 4 km ground block (x -1400..2600 m, y -1800..2200 m). All runs head +X.
AS50_AREAS_CM = {'lane': (-120000.0, -150000.0),       # M1-M10 start (runs up to ~1.6 km along +X)
                 'course': (-60000.0, -100000.0),      # M11 course origin (course x 0..1250 m, y -60..160 m from it)
                 'orbit': (140000.0, -100000.0)}       # M12 target (the ship starts 100 m off its +Y side)
AS50_MATS = {'idle': '/Engine/EditorMaterials/WidgetMaterial_Current', 'next': '/Engine/EditorMaterials/WidgetMaterial_Y',
             'passed': '/Engine/EditorMaterials/WidgetMaterial_Z', 'missed': '/Engine/EditorMaterials/WidgetMaterial_X',
             'target': '/Engine/EditorMaterials/WidgetMaterial_X', 'fallback': '/Engine/BasicShapes/BasicShapeMaterial'}
AS50_ANIM = ('WheelAngleDeg', 'TurbineYawDeg_L', 'TurbineYawDeg_R', 'NozzlePitchDeg_FL', 'NozzlePitchDeg_RR', 'RudderDeg',
             'ThrustAlpha_FL', 'NozzleFlareDeg_FL')
AS50_DEFAULTS = dict(schemes=[0, 1, 2, 3], net='standalone', runs=None, capture=True, capture_every=4,
                     chase_res=(1280, 720), still_res=(1920, 1080), capture_skills=('precise',), xgrab=False,
                     classic_crosscheck=False, auto_post=True, final_check=True, require_scheme=True, listen_captures=False,
                     pktlag_ms=100.0, real_fps_warn=12.0, max_wall_s=4 * 3600.0, max_chase_frames=2400, min_free_gb=6.0,
                     sloppy_repeats=3)


def as50_en(x):
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


def as50_same(a, b):
    try:
        return a is not None and b is not None and bool(a == b)
    except Exception:  # noqa: BLE001
        return False


def as50_rnd(d, n=4):
    if isinstance(d, float):
        return round(d, n)
    if isinstance(d, (list, tuple)):
        return [as50_rnd(x, n) for x in d]
    if isinstance(d, dict):
        return dict((k, as50_rnd(v, n)) for k, v in d.items())
    return d


class As50Run(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.listen = cfg['net'] == 'listen'
        self.R = {'version': AS50_VERSION, 'protocol': AS50P.PROTOCOL_VERSION, 'armed_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'cfg': dict((k, v if not isinstance(v, tuple) else list(v)) for k, v in cfg.items()), 'schemes': {},
                  'errors': {}, 'lines': [], 'done': False, 'reason': None, 'final_check': None}
        self.orig = {}
        self.handle = None
        self.phase = 'arming'
        self.wall0 = time.time()
        self.end_wall = None
        self.end_req = 0.0
        self.sw = self.cw = None          # server world / pilot (client) world; standalone: the same world
        self.pc = self.hpc = self.rpc = None
        self.char = None
        self.ship_s = self.ship_p = None  # server copy / pilot's copy (standalone: the same actor)
        self.hull_s = None
        self.mesh_p = self.anim_p = None
        self.sub = None
        self.caps = {}
        self.cap_world = None
        self.cap_dead = False
        self.gate_parts = {}
        self.mats = {}
        self.act = {}
        self.t_world0 = None
        self.tw_last = None
        self.now = 0.0
        self.frames = 0
        self.skipped = 0
        self.fps_samples = []
        self.real_fps = None
        self.D = {}
        self.si = -1
        self.scheme_id = None
        self.key = None
        self.ctx = None
        self.gen = None
        self.reset_state = None
        self.run_name = None
        self.run_idx = 0
        self.run_frames = 0
        self.run_wall0 = 0.0
        self.run_game0 = 0.0
        self.run_log = []
        self.run_stats = {}
        self.last_item = None
        self.fire_prev = False
        self.chase = None
        self.n_still = 0
        self.media = {}
        self.balls = set()
        self.balls_total = 0
        self.health_prev = None
        self.hull_hits = 0
        self.scheme_wall0 = 0.0
        self.scheme_game0 = 0.0
        self.confirm = {}
        self.boarded_once = False
        self.log_file = find_log()
        self.log_off = os.path.getsize(self.log_file) if self.log_file else 0
        self.log_marks = []
        self.user_play = False
        self.last_status = 0.0
        self.post_cmd = None

    # ================================================================ output
    def line(self, tag, msg):
        s = '%s: [%8.2f %s %s %s] %s' % (tag, self.now, self.phase, self.key or '-', self.run_name or '-', msg)
        self.R['lines'].append(s)
        if len(self.R['lines']) > 400:
            del self.R['lines'][:100]
        try:
            with open(os.path.join(AS50_CTRL, 'as50_log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def err(self, where):
        e = self.R['errors'].setdefault(where, {'n': 0, 'last': ''})
        e['n'] += 1
        e['last'] = traceback.format_exc()[-1500:]
        if e['n'] == 1:
            self.line('WARN', 'script error in %s: %s' % (where, e['last'].strip().splitlines()[-1]))

    def n_errors(self):
        return sum(e['n'] for e in self.R['errors'].values())

    def status_text(self):
        el = time.time() - self.wall0
        sch = self.cfg['schemes']
        L = ['%s  phase %s  net %s  armed %s' % (AS50_VERSION, self.phase, self.cfg['net'], self.R['armed_utc']),
             'scheme %s/%d %s  run %s  run game %.1f s (nominal %s s)  ctx frame %s' % (
                 self.si + 1, len(sch), self.key, self.run_name, self.run_frames / FIXED_FPS,
                 round(AS50P.nominal_s(self.run_name), 1) if self.run_name else '?', self.ctx.frame if self.ctx else '-'),
             'game %.1f s  wall %.0f s  real fps %s  frames %d (skipped %d)  ETA %s' % (
                 self.now, el, None if self.real_fps is None else round(self.real_fps, 1), self.frames, self.skipped, self.eta())]
        for k, v in self.R['schemes'].items():
            L.append('  %s: %s' % (k, v.get('summary')))
        L.append('errors %s' % dict((k, v['n']) for k, v in self.R['errors'].items()))
        for k, v in list(self.R['errors'].items())[-3:]:
            L.append('--- %s\n%s' % (k, v['last'][-600:]))
        for l in self.R['lines'][-14:]:
            L.append('  ' + l[:400])
        return '\n'.join(L)

    def eta(self):
        try:
            if self.real_fps is None or self.ctx is None:
                return '?'
            names = [n for n, _ in AS50P.plan(self.ctx)]
            rem = 0.0
            if self.run_name in names:
                i = names.index(self.run_name)
                rem += max(0.0, AS50P.nominal_s(self.run_name) - self.run_frames / FIXED_FPS)
                rem += sum(AS50P.nominal_s(n) + 1.5 for n in names[i + 1:])
            per_scheme = sum(AS50P.nominal_s(n) + 1.5 for n in names)
            rem += per_scheme * max(0, len(self.cfg['schemes']) - self.si - 1)
            return '%.0f min' % (rem * FIXED_FPS / max(1.0, self.real_fps) / 60.0)
        except Exception:  # noqa: BLE001
            return '?'

    def write_status(self, force=False):
        if not force and time.time() - self.last_status < 2.0:
            return
        self.last_status = time.time()
        try:
            with open(os.path.join(AS50_CTRL, 'status.txt'), 'w') as f:
                f.write(self.status_text() + '\n')
            self.R['phase'] = self.phase
            self.R['game_t'] = round(self.now, 2)
            self.R['wall_s'] = round(time.time() - self.wall0, 1)
            with open(os.path.join(AS50_CTRL, 'as50_result.json'), 'w') as f:
                json.dump(self.R, f, indent=1, default=str)
        except Exception:  # noqa: BLE001
            pass

    def sdir(self, key=None, *sub):
        d = os.path.join(AS50_CTRL, key or self.key, *sub)
        os.makedirs(d, exist_ok=True)
        return d

    # ================================================================ arm / restore
    def arm(self):
        os.makedirs(AS50_CTRL, exist_ok=True)
        with open(os.path.join(AS50_CTRL, 'as50_log.txt'), 'a') as f:
            f.write('\n==== %s armed %s cfg %s\n' % (AS50_VERSION, self.R['armed_utc'], self.R['cfg']))
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if les.is_in_play_in_editor():
            self.line('FAIL', 'PIE already running (the user plays?): not armed')
            return False
        ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        if MAP_NAME not in ew.get_path_name():
            self.line('FAIL', 'editor world is %s, not %s: open the map first' % (ew.get_path_name(), MAP_NAME))
            return False
        bad = [s for s in self.cfg['schemes'] if s not in AS50P.SCHEMES]
        if bad:
            self.line('FAIL', 'unknown scheme ids %s (0-3)' % bad)
            return False
        try:
            mem = [int(l.split()[1]) for l in open('/proc/meminfo') if l.startswith('MemAvailable')][0] / 1048576.0
            self.R['mem_available_gb'] = round(mem, 1)
            self.line('INFO' if mem >= 4 else 'WARN', 'MemAvailable %.1f GB' % mem)
        except Exception:  # noqa: BLE001
            pass
        try:
            free = shutil.disk_usage(AS50_CTRL).free / 1e9
            self.R['disk_free_gb'] = round(free, 1)
            if self.cfg['capture'] and free < self.cfg['min_free_gb']:
                self.cfg['capture'] = False
                self.line('WARN', 'only %.1f GB free on the Saved disk: captures off' % free)
        except Exception:  # noqa: BLE001
            pass
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
            if self.listen:
                tl_set(ps, {'PlayNetMode': 'PIE_ListenServer', 'PlayNumberOfClients': 2, 'RunUnderOneProcess': True})
            else:
                tl_set(ps, {'PlayNetMode': 'PIE_Standalone', 'PlayNumberOfClients': 1})
            self.line('INFO', 'play settings %s (were %s)' % ('Listen Server / 2 players' if self.listen else 'Standalone / 1 player', self.orig['play']))
        except Exception:  # noqa: BLE001
            self.err('play_settings')
        try:
            bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
            self.orig['burrower_enabled'] = bool(bcdo.get_editor_property('bEnabled'))
            bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('burrower_settings')
        for n in AS50_ACTIONS:
            try:
                self.act[n] = unreal.load_asset(AS50_IA + n)
                if self.act[n] is None:
                    self.line('WARN', 'input action %s not found' % n)
            except Exception:  # noqa: BLE001
                self.err('load_' + n)
        for k, p in AS50_MATS.items():
            try:
                self.mats[k] = unreal.load_asset(p)
            except Exception:  # noqa: BLE001
                self.mats[k] = None
        for k in list(self.mats):
            if self.mats[k] is None:
                self.mats[k] = self.mats.get('fallback')
        try:
            self.remove_temp()
            self.spawn_temp(eas)
        except Exception:  # noqa: BLE001
            self.err('spawn_temp')
            self.cap_dead = True
        with open(os.path.join(AS50_CTRL, 'as50_restore.json'), 'w') as f:
            json.dump(self.orig, f, indent=1, default=str)
        self.log_mark('arm')
        les.editor_request_begin_play()
        self.phase = 'wait_pie'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write_status(True)
        self.line('INFO', 'armed; PIE requested (schemes %s, net %s)' % (self.cfg['schemes'], self.cfg['net']))
        return True

    def spawn_temp(self, eas):
        CO = AS50P.B.C
        n = 0
        for name in ('Chase', 'Still'):
            cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0.0, 0.0, 0.0))
            cap.set_actor_label(AS50_TEMP + name)
            cc = cap.capture_component2d
            cc.set_editor_property('capture_every_frame', False)
            cc.set_editor_property('capture_on_movement', False)
            n += 1
        cyl = unreal.load_asset('/Engine/BasicShapes/Cylinder')
        cube = unreal.load_asset('/Engine/BasicShapes/Cube')
        sphere = unreal.load_asset('/Engine/BasicShapes/Sphere')
        ox, oy = AS50_AREAS_CM['course']
        z0 = AS50_GROUND_TOP + AS50P.COURSE_AGL_M * 100.0
        hw, hh = CO.GATE_W * 50.0, CO.GATE_H * 50.0           # half width / height (cm) of the gate frame
        post_r, bar = 75.0, 100.0

        def part(mesh, label, loc, rot_yaw, scale):
            a = eas.spawn_actor_from_object(mesh, unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(rot_yaw)))
            a.set_actor_label(label)
            a.set_actor_scale3d(unreal.Vector(*scale))
            smc = a.static_mesh_component
            smc.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
            smc.set_collision_profile_name('NoCollision')      # no traces (the ship's ground traces, the camera)
            if self.mats.get('idle'):
                smc.set_material(0, self.mats['idle'])
            return a
        for gname, x, y, z, face in CO.GATES:
            c = (ox + x * 100.0, oy + y * 100.0, z0 + z * 100.0)
            fy = math.radians(face)
            lat = (-math.sin(fy), math.cos(fy))
            top = c[2] + hh
            for side, sg in (('PostL', -1.0), ('PostR', 1.0)):
                px, py = c[0] + lat[0] * sg * (hw + post_r), c[1] + lat[1] * sg * (hw + post_r)
                hgt = top + bar - AS50_GROUND_TOP
                part(cyl, '%sGate_%s_%s' % (AS50_TEMP, gname, side), (px, py, AS50_GROUND_TOP + hgt / 2.0), 0.0,
                     (2 * post_r / 100.0, 2 * post_r / 100.0, hgt / 100.0))
                n += 1
            span = (2 * hw + 4 * post_r) / 100.0
            part(cube, '%sGate_%s_Top' % (AS50_TEMP, gname), (c[0], c[1], top + bar / 2.0), face, (bar / 100.0, span, bar / 100.0))
            part(cube, '%sGate_%s_Sill' % (AS50_TEMP, gname), (c[0], c[1], c[2] - hh - 30.0), face, (0.6, span, 0.6))
            n += 2
        tx, ty = AS50_AREAS_CM['orbit']
        t = eas.spawn_actor_from_object(sphere, unreal.Vector(tx, ty, AS50_GROUND_TOP + AS50P.START_AGL_M * 100.0), unreal.Rotator(0.0, 0.0, 0.0))
        t.set_actor_label(AS50_TEMP + 'Target')
        t.set_actor_scale3d(unreal.Vector(12.0, 12.0, 12.0))          # radius 6 m: the bench's aim target (metrics.m12)
        smc = t.static_mesh_component
        smc.set_editor_property('mobility', unreal.ComponentMobility.MOVABLE)
        smc.set_collision_profile_name('BlockAll')                   # blocks Visibility: ComputeLocalAimPoint hits it
        if self.mats.get('target'):
            smc.set_material(0, self.mats['target'])
        n += 1
        self.line('INFO', 'placed %d %s* actors in the editor level (removed after PIE, the map is not saved)' % (n, AS50_TEMP))

    def remove_temp(self):
        try:
            eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
            n = 0
            for a in eas.get_all_level_actors():
                try:
                    if a.get_actor_label().startswith(AS50_TEMP):
                        eas.destroy_actor(a)
                        n += 1
                except Exception:  # noqa: BLE001
                    continue
            if n:
                self.line('INFO', 'removed %d %s* actors from the editor level' % (n, AS50_TEMP))
            return n
        except Exception:  # noqa: BLE001
            self.err('remove_temp')
            return -1

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
                v = {'PlayNetMode': str(self.orig['play'].get('PlayNetMode', 'PIE_Standalone')).split('.')[-1],
                     'PlayNumberOfClients': int(self.orig['play'].get('PlayNumberOfClients', 1))}
                if 'RunUnderOneProcess' in self.orig['play']:
                    v['RunUnderOneProcess'] = bool(self.orig['play']['RunUnderOneProcess'])
                tl_set(ps, v)
        except Exception:  # noqa: BLE001
            self.err('restore_play')
        try:
            if 'burrower_enabled' in self.orig:
                bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
                bcdo.set_editor_property('bEnabled', self.orig['burrower_enabled'], unreal.PropertyAccessChangeNotifyMode.NEVER)
        except Exception:  # noqa: BLE001
            self.err('restore_burrower')

    # ================================================================ finish
    def finish(self, reason):
        if self.phase in ('ending', 'finished'):
            return
        self.line('INFO', 'finishing: %s' % reason)
        self.R['reason'] = reason
        self.chase_off()
        try:
            if self.ship_p is not None and valid(self.ship_p):
                self.ship_p.debug_clear_input()
        except Exception:  # noqa: BLE001
            pass
        if self.ctx is not None and self.phase in ('gen', 'switch'):
            try:
                self.flush_run()
                self.write_scheme(getattr(self.ctx, 'frags', {}) or {}, 'interrupted: %s' % reason)
            except Exception:  # noqa: BLE001
                self.err('write_partial')
        for w in (self.sw, self.cw):
            try:
                if w is not None and self.listen:
                    unreal.SystemLibrary.execute_console_command(w, 'Net PktLag=0')
            except Exception:  # noqa: BLE001
                pass
        self.log_mark('end')
        self.scan_log_final()
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor() and not self.user_play:
            les.editor_request_end_play()
            self.end_req = time.time()
        self.phase = 'ending'
        self.end_wall = time.time()
        self.write_status(True)

    def end_tick(self):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        in_pie = les.is_in_play_in_editor()
        if in_pie and not self.user_play:
            if time.time() - self.end_wall < 120.0:
                if time.time() - self.end_req > 5.0:
                    les.editor_request_end_play()
                    self.end_req = time.time()
                return
            self.line('WARN', 'PIE did not end in 120 s: settings restored, TEMP actors left (run as_50x_stop.py after PIE)')
        self.restore()
        if not les.is_in_play_in_editor():
            self.remove_temp()
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        self.phase = 'finished'
        self.R['done'] = True
        try:
            AS50P.write_compare(AS50_CTRL)
        except Exception:  # noqa: BLE001
            self.err('compare_md')
        self.launch_post()
        self.write_status(True)
        self.line('INFO', 'done (%s); results in %s' % (self.R.get('reason'), AS50_CTRL))
        self.write_status(True)

    def launch_post(self):
        if not self.cfg.get('auto_post'):
            return
        post = os.path.join(AS50_W, 'Docs', 'Airship', 'scripts', 'harness', 'as_50_post.py')
        cmd = ['/usr/bin/python3', '-I', post, '--root', AS50_CTRL]
        self.post_cmd = ' '.join(cmd)
        try:
            env = dict((k, v) for k, v in os.environ.items() if not k.startswith('PYTHON') and k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD'))
            log = open(os.path.join(AS50_CTRL, 'post_log.txt'), 'a')
            subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=AS50_CTRL, env=env,
                             start_new_session=True, close_fds=True)
            self.line('INFO', 'post step started in the background: %s (log post_log.txt)' % self.post_cmd)
        except Exception:  # noqa: BLE001
            self.err('launch_post')
            self.line('WARN', 'post step not started; run it by hand: %s' % self.post_cmd)

    # ================================================================ log
    def log_mark(self, name):
        try:
            self.log_marks.append((name, os.path.getsize(self.log_file) if self.log_file else 0, round(self.now, 2)))
        except Exception:  # noqa: BLE001
            pass

    def log_since(self, name):
        """Log lines written since the mark `name` (the latest of that name)."""
        if not self.log_file:
            return []
        off = None
        for n, o, _ in self.log_marks:
            if n == name:
                off = o
        if off is None:
            return []
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(off)
                return f.read().splitlines()
        except Exception:  # noqa: BLE001
            self.err('log_since')
            return []

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

    def scan_log_final(self):
        if not self.log_file:
            return
        try:
            with open(self.log_file, 'r', errors='replace') as f:
                f.seek(self.log_off)
                lines = f.read().splitlines()
            pats = {'airship': 'LogAirship', 'airship_warn': 'LogAirship: Warning', 'error': 'Error:', 'ensure': 'Ensure condition failed',
                    'accessed_none': 'Accessed None', 'scheme': 'Aura.Airship.Scheme', 'user_play': 'Repeating last play command',
                    'hard_snap': 'Hard snap'}
            sc = {}
            for k, p in pats.items():
                hit = [l for l in lines if p in l]
                sc[k] = {'count': len(hit), 'sample': hit[:10] + (hit[-5:] if len(hit) > 15 else [])}
            self.R['log_scan'] = sc
            if sc['user_play']['count']:
                self.user_play = True
            if any(n == 'scheme_check' for n, _, _ in self.log_marks):
                chk = [l for l in self.log_since('scheme_check') if 'Scheme' in l or 'differ' in l]
                self.R['final_check'] = chk[:80]
        except Exception:  # noqa: BLE001
            self.err('scan_log')

    # ================================================================ PIE helpers
    def cmd(self, w, c):
        unreal.SystemLibrary.execute_console_command(w, c)
        self.line('INFO', 'console (%s): %s' % ('server' if as50_same(w, self.sw) else 'client', c))

    def subsystem(self, w):
        for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem):
            try:
                lp = s.get_outer()
                if lp.get_class().get_name() == 'LocalPlayer' and as50_same(lp.get_world(), w):
                    return s
            except Exception:  # noqa: BLE001
                pass
        return None

    def inject(self, name, x, y=0.0):
        a = self.act.get(name)
        if a is None or self.sub is None:
            return
        try:
            self.sub.inject_input_vector_for_action(a, unreal.Vector(float(x), float(y), 0.0), [], [])
        except Exception:  # noqa: BLE001
            self.err('inject_' + name)

    def set_cam(self, yaw, pitch):
        try:
            self.pc.set_control_rotation(unreal.Rotator(0.0, float(pitch), float(yaw)))
        except Exception:  # noqa: BLE001
            self.err('set_cam')

    def tele(self, ship):
        try:
            return parse_struct(ship.get_flight_telemetry().export_text())
        except Exception:  # noqa: BLE001
            self.err('tele')
            return {}

    def anim_vals(self):
        out = {}
        if self.anim_p is None:
            try:
                self.anim_p = self.mesh_p.get_anim_instance()
            except Exception:  # noqa: BLE001
                return out
            if self.anim_p is None:
                return out
        for n in AS50_ANIM:
            try:
                out[n] = float(self.anim_p.get_editor_property(n))
            except Exception:  # noqa: BLE001
                out[n] = None
        return out

    def count_balls(self):
        """Cannonballs fired so far this scheme (server world): balls that are new this frame (by name, so a name the engine
        reuses after an old ball is gone still counts)."""
        if not (self.run_name or '').startswith('m12'):
            return self.balls_total
        try:
            cls = unreal.load_class(None, BALL_CLS)
            alive = set(b.get_name() for b in unreal.GameplayStatics.get_all_actors_of_class(self.sw, cls))
            self.balls_total += len(alive - self.balls)
            self.balls = alive
        except Exception:  # noqa: BLE001
            self.err('balls')
        return self.balls_total

    def side_name(self, ship):
        try:
            n = as50_en(ship.get_aim_side()).upper()
            return 'port' if 'PORT' in n else 'stbd'
        except Exception:  # noqa: BLE001
            self.err('aim_side')
            return None

    def read_record(self):
        ts = self.tele(self.ship_s)
        loc, vel = v3(self.ship_s.get_actor_location()), v3(self.ship_s.get_velocity())
        rec = AS50P.derive(dict(ts), loc, vel)
        if self.listen:
            tp = self.tele(self.ship_p)
            view = AS50P.derive(dict(tp), v3(self.ship_p.get_actor_location()), v3(self.ship_p.get_velocity()))
        else:
            view = AS50P.derive(dict(ts), loc, vel)
        rot = self.pc.get_control_rotation()
        cam = [0.0, 0.0, 0.0]
        try:
            cm = unreal.GameplayStatics.get_player_camera_manager(self.cw, 0)
            cam = [c / 100.0 for c in v3(cm.get_camera_location())]
        except Exception:  # noqa: BLE001
            self.err('camera_loc')
        an = self.anim_vals()
        rec['pilot'] = {'view': view, 'screen': view, 'control_yaw': wrap180(float(rot.yaw)), 'control_pitch': wrap180(float(rot.pitch)),
                        'cam_loc_m': cam, 'TurbineYawDeg': an.get('TurbineYawDeg_L'), 'WheelAngleDeg': an.get('WheelAngleDeg'),
                        'NozzlePitchDeg': an.get('NozzlePitchDeg_FL'), 'aim_side': self.side_name(self.ship_p), 'anim': an}
        gc = ts.get('GroundClearanceM')
        rec['ground_contact'] = gc is not None and 0.0 <= gc < AS50P.GROUND_CONTACT_M
        rec['shots_total'] = self.count_balls()
        h = ts.get('Health')
        if h is not None and self.health_prev is not None and h < self.health_prev - 0.5:
            self.hull_hits += 1
            self.line('WARN', 'hull hit: health %.0f -> %.0f at %s' % (self.health_prev, h, r(loc, 0)))
        self.health_prev = h
        return rec

    def log_frame(self, rec, item, seg=None):
        try:
            d = {'f': self.ctx.frame if self.ctx else 0, 'w': round(self.now, 3), 'sg': seg or (item.seg if item else '?'),
                 'T': as50_rnd(dict((k, rec[k]) for k in AS50P.TELEMETRY_FIELDS if k in rec)),
                 'loc': as50_rnd(list(rec['ActorLocCm']), 1), 'vel': as50_rnd(list(rec['VelCm']), 1),
                 'cy': round(rec['pilot']['control_yaw'], 3), 'cp': round(rec['pilot']['control_pitch'], 3),
                 'cam': as50_rnd(rec['pilot']['cam_loc_m'], 2), 'an': as50_rnd(rec['pilot'].get('anim') or {}, 3),
                 'aim': (rec['pilot'].get('aim_side') or '?')[0], 'gc': int(bool(rec['ground_contact'])), 'sh': rec['shots_total']}
            if self.listen:
                pv = rec['pilot']['view']
                d['P'] = as50_rnd(dict((k, pv[k]) for k in AS50P.TELEMETRY_FIELDS if k in pv))
                d['Ploc'] = as50_rnd(list(pv['ActorLocCm']), 1)
            if item is not None and item.raw is not None:
                w = item.raw
                d['raw'] = [round(w.throttle, 3), round(w.steer, 3), round(w.lift, 3), round(w.strafe, 3), int(bool(w.boost)),
                            int(bool(w.brake)), int(bool(w.aim)), int(bool(w.fire)), None if w.cam_yaw is None else round(w.cam_yaw, 3),
                            None if w.cam_pitch is None else round(w.cam_pitch, 3), int(bool(w.look))]
            if item is not None and item.debug is not None:
                d['dbg'] = item.debug
            self.run_log.append(d)
        except Exception:  # noqa: BLE001
            self.err('log_frame')

    def flush_run(self):
        if not self.run_name or self.key is None:
            return
        try:
            d = self.sdir(self.key, 'telemetry_parts')
            tag = '' if not self.listen else '_lat100'
            with open(os.path.join(d, '%02d_%s%s.json' % (self.run_idx, self.run_name, tag)), 'w') as f:
                json.dump({'run': self.run_name, 'frames': self.run_log, 'notes': (self.ctx.notes.get(self.run_name) if self.ctx else None)},
                          f, separators=(',', ':'), default=str)
        except Exception:  # noqa: BLE001
            self.err('flush_run')
        self.run_stats[self.run_name] = {'frames': self.run_frames, 'game_s': round(self.run_frames / FIXED_FPS, 2),
                                         'wall_s': round(time.time() - self.run_wall0, 1)}
        self.run_log = []

    def combine_telemetry(self, key):
        d = os.path.join(AS50_CTRL, key, 'telemetry_parts')
        if not os.path.isdir(d):
            return None
        tag = '' if not self.listen else '_lat100'
        names = sorted(n for n in os.listdir(d) if n.endswith(tag + '.json') and (self.listen or not n.endswith('_lat100.json')))
        out = os.path.join(AS50_CTRL, key, 'telemetry%s.json' % tag)
        try:
            with open(out, 'w') as f:
                f.write('{"scheme": %s, "harness": %s, "fps": %d, "runs": {' % (json.dumps(key), json.dumps(AS50_VERSION), int(FIXED_FPS)))
                for i, n in enumerate(names):
                    run = n[3:-5]
                    f.write(('' if i == 0 else ',') + '%s:' % json.dumps(run))
                    with open(os.path.join(d, n)) as g:
                        f.write(g.read())
                f.write('}}')
            for n in names:
                os.remove(os.path.join(d, n))
            if not os.listdir(d):
                os.rmdir(d)
            return out
        except Exception:  # noqa: BLE001
            self.err('combine_telemetry')
            return None

    # ================================================================ captures
    def cap_init(self):
        if self.cap_dead or not self.cfg['capture'] or (self.listen and not self.cfg.get('listen_captures')):
            return False
        if self.caps:
            return True
        try:
            for name, res in (('chase', self.cfg['chase_res']), ('still', self.cfg['still_res'])):
                lab = AS50_TEMP + name.capitalize()
                act = [a for a in unreal.GameplayStatics.get_all_actors_of_class(self.cap_world, unreal.SceneCapture2D) if a.get_actor_label() == lab]
                if not act:
                    self.line('WARN', 'no %s in the PIE world: no captures' % lab)
                    self.cap_dead = True
                    return False
                rt = unreal.RenderingLibrary.create_render_target2d(self.cap_world, int(res[0]), int(res[1]), unreal.TextureRenderTargetFormat.RTF_RGBA8)
                cc = act[0].capture_component2d
                cc.set_editor_property('texture_target', rt)
                cc.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                cc.set_editor_property('capture_every_frame', False)
                cc.set_editor_property('capture_on_movement', False)
                cc.set_editor_property('always_persist_rendering_state', True)
                self.caps[name] = (act[0], cc, rt)
            return True
        except Exception:  # noqa: BLE001
            self.err('cap_init')
            self.cap_dead = True
            return False

    def capture(self, which, view, folder, fname):
        if not self.cap_init():
            return None
        try:
            a, cc, rt = self.caps[which]
            if view == 'pilot':
                cm = unreal.GameplayStatics.get_player_camera_manager(self.cap_world, 0)
                frm, rot, fov = cm.get_camera_location(), cm.get_camera_rotation(), cm.get_fov_angle()
            else:      # wide: 120 m behind, 30 m to port, 60 m above the ship, looking 80 m ahead of it
                loc = v3(self.ship_p.get_actor_location())
                fwd = v3(self.ship_p.get_actor_forward_vector())
                rgt = v3(self.ship_p.get_actor_right_vector())
                f2 = math.hypot(fwd[0], fwd[1]) or 1.0
                fh, rh = (fwd[0] / f2, fwd[1] / f2), (rgt[0], rgt[1])
                frm = unreal.Vector(loc[0] - fh[0] * 12000.0 - rh[0] * 3000.0, loc[1] - fh[1] * 12000.0 - rh[1] * 3000.0, loc[2] + 6000.0)
                to = unreal.Vector(loc[0] + fh[0] * 8000.0, loc[1] + fh[1] * 8000.0, loc[2])
                rot, fov = unreal.MathLibrary.find_look_at_rotation(frm, to), 70.0
            cc.set_editor_property('fov_angle', float(fov))
            a.set_actor_location_and_rotation(frm, rot, False, True)
            cc.capture_scene()
            os.makedirs(folder, exist_ok=True)
            unreal.RenderingLibrary.export_render_target(self.cap_world, rt, folder, fname)
            return os.path.join(folder, fname)
        except Exception:  # noqa: BLE001
            self.err('capture_' + which)
            return None

    def chase_on(self, run):
        if not self.cap_init():
            return
        d = self.sdir(self.key, 'chase')
        for n in os.listdir(d):
            if n.startswith('chase_') and n.endswith('.png'):
                try:
                    os.remove(os.path.join(d, n))
                except Exception:  # noqa: BLE001
                    pass
        self.chase = {'run': run, 'n': 0, 'idx': 0, 'meta': [], 'dir': d, 'every': max(1, int(self.cfg['capture_every']))}
        self.chase_frame()

    def chase_frame(self):
        c = self.chase
        if c is None:
            return
        if c['n'] % c['every'] == 0 and c['idx'] < self.cfg['max_chase_frames']:
            fn = 'chase_%05d.png' % c['idx']
            if self.capture('chase', 'pilot', c['dir'], fn):
                rec = self.ctx.last if self.ctx else {}
                pv = (rec.get('pilot') or {}).get('view') or {}
                c['meta'].append({'i': c['idx'], 'file': fn, 'frame': self.ctx.frame if self.ctx else None, 't': round(self.ctx.time, 3) if self.ctx else None,
                                  'speed_ms': round(pv.get('ForwardSpeedMS') or 0.0, 1), 'alt_m': round(rec.get('AltitudeM') or 0.0, 1),
                                  'next_gate': (self.ctx.shared.get('next_gate') if self.ctx else None),
                                  'drift': bool(rec.get('bDrifting')), 'boost': round(rec.get('Boost') or 0.0, 2),
                                  'turbo': round(rec.get('TurboAlpha') or 0.0, 2), 'steer': round(rec.get('Steer') or 0.0, 2)})
                c['idx'] += 1
        c['n'] += 1

    def chase_off(self):
        c = self.chase
        self.chase = None
        if c is None:
            return
        try:
            with open(os.path.join(c['dir'], 'frames.json'), 'w') as f:
                json.dump({'scheme': self.key, 'run': c['run'], 'fps': FIXED_FPS / c['every'], 'every': c['every'],
                           'res': list(self.cfg['chase_res']), 'frames': c['meta']}, f, indent=0)
            self.media['chase'] = '%s/chase (%d frames)' % (self.key, c['idx'])
            self.line('INFO', 'chase capture: %d frames in %s' % (c['idx'], c['dir']))
        except Exception:  # noqa: BLE001
            self.err('chase_off')

    def still(self, label):
        d = self.sdir(self.key, 'stills')
        self.n_still += 1
        base = '%02d_%s' % (self.n_still, label)
        got = [self.capture('still', v, d, '%s_%s.png' % (base, v)) for v in ('pilot', 'wide')]
        if any(got):
            self.media.setdefault('stills', []).append(base)
            self.line('INFO', 'still %s (t %.2f s)' % (base, self.ctx.time if self.ctx else -1))
        if self.cfg.get('xgrab'):
            try:
                xg = os.path.join(AS50_CTRL, 'xgrab')
                os.makedirs(xg, exist_ok=True)
                with open(os.path.join(xg, '%s_%s.req' % (self.key, base)), 'w') as f:
                    f.write(xg + '\n')
            except Exception:  # noqa: BLE001
                self.err('xgrab')

    def gate_color(self, name, status):
        if not self.gate_parts or (self.listen and not self.cfg.get('listen_captures')):
            return
        try:
            CO = AS50P.B.C
            if status == 'next' and name == CO.GATES[0][0]:
                for parts in self.gate_parts.values():
                    for a in parts:
                        a.static_mesh_component.set_material(0, self.mats['idle'])
            m = self.mats.get(status) or self.mats.get('idle')
            for a in self.gate_parts.get(name, []):
                a.static_mesh_component.set_material(0, m)
        except Exception:  # noqa: BLE001
            self.err('gate_color')

    # ================================================================ state machine
    def tick(self, dt):
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            self.err('tick')
            if self.n_errors() > 300 and self.phase not in ('ending', 'finished'):
                self.finish('too many script errors')
        self.write_status()

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
        if globals().get('AS50_STOP'):
            self.finish('stopped by as_50x_stop.py')
            return
        if time.time() - self.wall0 > self.cfg['max_wall_s']:
            self.finish('max wall time %.0f s reached' % self.cfg['max_wall_s'])
            return
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.phase == 'wait_pie':
            ws = [w for w in unreal.EditorLevelLibrary.get_pie_worlds(False) if MAP_NAME in w.get_path_name()]
            if not self.listen and ws:
                self.sw = self.cw = ws[0]
            elif self.listen:
                sv = [w for w in ws if self.role(w) == 'server']
                cl = [w for w in ws if self.role(w) == 'client']
                if sv and cl:
                    self.sw, self.cw = sv[0], cl[0]
                elif ws and time.time() - self.wall0 > 60 and not cl:
                    self.finish('listen mode: no client world in 60 s (roles %s): set the play mode with '
                                'Docs/Airship/scripts/harness/set_play_mode.sh listen 2 (editor closed)' % [self.role(w) for w in ws])
                    return
            if self.sw is not None:
                self.cap_world = self.cw
                self.phase = 'wait_actors'
                self.line('INFO', 'PIE world(s): %s' % ([self.sw.get_path_name()] + ([self.cw.get_path_name()] if self.listen else [])))
            elif time.time() - self.wall0 > 240:
                self.finish('PIE did not start in 240 s')
            return
        if not les.is_in_play_in_editor():
            self.finish('PIE ended before the test finished')
            return
        tw = unreal.GameplayStatics.get_time_seconds(self.sw)
        if self.tw_last is not None:
            dtw = tw - self.tw_last
            if dtw < 0.5 / FIXED_FPS:
                return                     # no new world frame (paused, or an extra Slate tick)
            if dtw > 1.5 / FIXED_FPS:
                self.skipped += 1
                if self.skipped == 1:
                    self.line('WARN', 'a world frame of %.3f s (fixed %.3f): frames are being skipped' % (dtw, 1.0 / FIXED_FPS))
        self.tw_last = tw
        if self.t_world0 is None:
            self.t_world0 = tw
        self.now = tw - self.t_world0
        self.frames += 1
        self.fps_sample()
        if self.phase == 'wait_actors':
            if self.find_actors():
                self.phase = 'board'
                self.D = {'f': 0}
            elif self.now > 30:
                self.finish('actors not found after 30 s: %s' % self.R.get('setup_try'))
            return
        self.scan_user_play()
        if self.user_play:
            self.finish('the user pressed Play (Repeating last play command): stopping the test, PIE left running')
            return
        if not valid(self.ship_s) or not valid(self.ship_p):
            self.finish('the ship is gone')
            return
        getattr(self, 'tick_' + self.phase)()

    def fps_sample(self):
        now = time.time()
        self.fps_samples.append((now, self.frames))
        while len(self.fps_samples) > 2 and now - self.fps_samples[0][0] > 30.0:
            del self.fps_samples[0]
        if len(self.fps_samples) > 10 and now - self.fps_samples[0][0] > 2.0:
            self.real_fps = (self.frames - self.fps_samples[0][1]) / (now - self.fps_samples[0][0])
            if self.real_fps < self.cfg['real_fps_warn'] and not self.D.get('_fpswarn'):
                self.D['_fpswarn'] = True
                self.line('WARN', 'real fps %.1f: editor on a hidden workspace? (game time stays right, wall time grows; '
                                  'in listen mode PktLag is real time: the lag in game time shrinks)' % self.real_fps)

    def find_actors(self):
        try:
            ship_cls = unreal.load_class(None, SHIP_CLS)
            if not self.listen:
                self.pc = unreal.GameplayStatics.get_player_controller(self.sw, 0)
                self.char = self.pc.get_controlled_pawn() if self.pc else None
                ss = unreal.GameplayStatics.get_all_actors_of_class(self.sw, ship_cls)
                self.ship_s = self.ship_p = ss[0] if ss else None
                self.sub = self.subsystem(self.sw)
            else:
                self.hpc = unreal.GameplayStatics.get_player_controller(self.sw, 0)
                rem = [p for p in unreal.GameplayStatics.get_all_actors_of_class(self.sw, unreal.PlayerController) if not p.is_local_controller()]
                self.rpc = rem[0] if rem else None
                self.pc = unreal.GameplayStatics.get_player_controller(self.cw, 0)
                self.char = self.pc.get_controlled_pawn() if self.pc else None
                ss = unreal.GameplayStatics.get_all_actors_of_class(self.sw, ship_cls)
                cs = unreal.GameplayStatics.get_all_actors_of_class(self.cw, ship_cls)
                self.ship_s = ss[0] if ss else None
                self.ship_p = next((s for s in cs if self.ship_s and s.get_name() == self.ship_s.get_name()), None)
                self.sub = self.subsystem(self.cw)
            self.R['setup_try'] = {'pc': bool(self.pc), 'char': bool(self.char), 'ship_s': bool(self.ship_s), 'ship_p': bool(self.ship_p),
                                   'sub': bool(self.sub), 'rpc': bool(self.rpc) if self.listen else None}
            if not (self.pc and self.char and self.ship_s and self.ship_p and self.sub and (self.rpc or not self.listen)):
                return False
            self.hull_s = self.ship_s.get_editor_property('HullCollision')
            self.mesh_p = self.ship_p.get_editor_property('Mesh')
            self.anim_p = self.mesh_p.get_anim_instance()
            self.mesh_p.set_editor_property('visibility_based_anim_tick_option',
                                            unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES,
                                            unreal.PropertyAccessChangeNotifyMode.NEVER)
            self.gate_parts = {}
            for a in unreal.GameplayStatics.get_all_actors_of_class(self.cap_world, unreal.StaticMeshActor):
                try:
                    lab = a.get_actor_label()
                except Exception:  # noqa: BLE001
                    continue
                if lab.startswith(AS50_TEMP + 'Gate_'):
                    self.gate_parts.setdefault(lab.split('_')[3], []).append(a)
            self.R['setup'] = {'world': self.sw.get_path_name(), 'pilot_world': self.cw.get_path_name(), 'char': self.char.get_name(),
                               'ship': self.ship_s.get_name(), 'anim': self.anim_p.get_class().get_name() if self.anim_p else None,
                               'gates_found': sorted(self.gate_parts), 'roles': (as50_en(self.ship_s.get_local_role()), as50_en(self.ship_p.get_local_role()))}
            self.line('INFO', 'setup %s' % self.R['setup'])
            return True
        except Exception:  # noqa: BLE001
            self.err('find_actors')
            return False

    def possessed(self):
        try:
            return as50_same(self.pc.get_controlled_pawn(), self.ship_p)
        except Exception:  # noqa: BLE001
            return False

    # ---- board (once)
    def tick_board(self):
        D = self.D
        D['f'] += 1
        f = D['f']
        if f == 2:
            self.cmd(self.sw, 'Aura.Airship.Board %d' % (1 if self.listen else 0))
        if f > 2 and self.possessed():
            self.line('INFO', 'boarded after %d frames (pilot %s)' % (f - 2, self.ship_s.get_pilot().get_name() if self.ship_s.get_pilot() else None))
            self.boarded_once = True
            if self.listen:
                self.phase = 'lag'
                self.D = {'f': 0, 'wall0': time.time(), 'f0': self.frames}
            else:
                self.next_scheme()
            return
        if self.listen and f == 90 and not self.possessed():
            try:     # index 1 was not the client: whoever got the helm leaves, then the other index
                if self.ship_s.has_pilot():
                    self.cmd(self.sw, 'Aura.Airship.Exit 1')
                D['retry'] = True
            except Exception:  # noqa: BLE001
                self.err('board_retry')
        if self.listen and f == 120 and D.get('retry'):
            self.cmd(self.sw, 'Aura.Airship.Board 0')
        if f > 210:
            self.finish('could not board the ship (Aura.Airship.Board; pilot %s)' % (self.ship_s.get_pilot().get_name() if self.ship_s.get_pilot() else None))

    # ---- listen: Net PktLag from the real fps (as_45: PktLag is real time)
    def tick_lag(self):
        D = self.D
        D['f'] += 1
        if D['f'] == 60:
            fps = (self.frames - D['f0']) / max(0.01, time.time() - D['wall0'])
            n = int(round(max(self.cfg['pktlag_ms'], min(1000.0, self.cfg['pktlag_ms'] * FIXED_FPS / max(1.0, fps)))))
            self.R['pktlag'] = {'real_fps': round(fps, 2), 'pktlag_ms': n}
            self.cmd(self.cw, 'Net PktLag=%d' % n)
            self.cmd(self.sw, 'Net PktLag=%d' % n)
        if D['f'] >= 90:
            self.next_scheme()

    # ---- the next scheme: console switch, confirmation, inertia log, then the protocol
    def next_scheme(self):
        self.si += 1
        if self.si >= len(self.cfg['schemes']):
            if self.cfg.get('final_check') and not self.listen:
                self.phase = 'final'
                self.D = {'f': 0}
                self.key = 'classic'
            else:
                self.finish('all schemes done')
            return
        self.scheme_id = self.cfg['schemes'][self.si]
        self.key = AS50P.SCHEMES[self.scheme_id][0]
        self.run_name = None
        self.run_idx = 0
        self.run_stats = {}
        self.media = {}
        self.n_still = 0
        self.balls = set()
        self.balls_total = 0
        self.hull_hits = 0
        self.confirm = {}
        self.scheme_wall0 = time.time()
        self.scheme_game0 = self.now
        self.sdir(self.key)
        self.log_mark('scheme_' + self.key)
        self.phase = 'switch'
        self.D = {'f': 0}
        self.cmd(self.sw, 'Aura.Airship.Scheme %d' % self.scheme_id)
        self.R['schemes'][self.key] = {'summary': 'switching'}

    def scheme_state(self):
        """What the C++ says the scheme is on the server and on the pilot's copy."""
        out = {}
        want = AS50P.SCHEMES[self.scheme_id][2]
        for tag, ship in (('server', self.ship_s), ('pilot', self.ship_p)):
            if tag == 'pilot' and not self.listen:
                continue
            d = {}
            try:
                d['get_control_scheme'] = as50_en(ship.get_control_scheme()).upper()
            except Exception as e:  # noqa: BLE001
                d['get_control_scheme'] = 'n/a (%s)' % e.__class__.__name__
            t = self.tele(ship)
            d['telemetry_scheme'] = t.get('Scheme')
            d['ok'] = (d['get_control_scheme'].replace('_', '') == want.replace('_', '')) or (t.get('Scheme') is not None and int(round(t['Scheme'])) == self.scheme_id)
            d['known'] = not d['get_control_scheme'].startswith('n/a') or t.get('Scheme') is not None
            out[tag] = d
        return out

    def tick_switch(self):
        D = self.D
        D['f'] += 1
        f = D['f']
        if f == 15 or f == 45:
            st = self.scheme_state()
            ok = all(v['ok'] for v in st.values())
            known = any(v['known'] for v in st.values())
            self.confirm = {'want': self.scheme_id, 'state': st, 'ok': ok, 'attempt': 'console' if f == 15 else 'set_control_scheme'}
            if ok or (not known and self.scheme_id == 0):
                if not ok:
                    self.line('WARN', 'the C++ reports no scheme (no GetControlScheme / telemetry Scheme): Classic = v1, measured as is')
                    self.confirm['note'] = 'unconfirmed: no contract in this build (Classic = v1)'
                D['go'] = f + 1
                self.cmd(self.sw, 'Aura.Airship.Telemetry')
                self.cmd(self.sw, 'Aura.Airship.Scheme')
            elif f == 15:
                self.line('WARN', 'scheme %d not confirmed after the console command (%s): trying SetControlScheme' % (self.scheme_id, st))
                try:
                    en = getattr(unreal, 'AirshipControlScheme')
                    self.ship_s.set_control_scheme(getattr(en, AS50P.SCHEMES[self.scheme_id][2]))
                except Exception:  # noqa: BLE001
                    self.err('set_control_scheme')
            else:
                msg = 'scheme %d (%s) not confirmed: %s' % (self.scheme_id, self.key, st)
                if self.cfg.get('require_scheme', True):
                    self.line('FAIL', msg + ': skipped')
                    self.R['schemes'][self.key] = {'summary': 'skipped (scheme not confirmed)', 'confirm': self.confirm}
                    self.write_scheme({}, 'skipped: scheme not confirmed')
                    self.next_scheme()
                    return
                self.line('WARN', msg + ': measured anyway (require_scheme False)')
                D['go'] = f + 1
        if D.get('go') and f >= D['go'] + 5:
            self.start_pass()

    def start_pass(self):
        areas = dict((k, dict(x_m=v[0] / 100.0, y_m=v[1] / 100.0, ground_m=AS50_GROUND_TOP / 100.0)) for k, v in AS50_AREAS_CM.items())
        cfg = dict(self.cfg)
        self.ctx = AS50P.Ctx(self.key, cfg, net='client' if self.listen else 'host', areas=areas)
        self.ctx.log_fn = self.line
        self.ctx.frags = {}
        if self.listen:
            base = self.load_metrics(self.key)
            sh = ((base or {}).get('meta') or {}).get('shared') or {}
            self.ctx.shared.update(dict((k, v) for k, v in sh.items() if v is not None))
            self.line('INFO', 'listen pass: shared values from the standalone metrics.json: %s' % sh)
        self.gen = AS50P.scheme_pass(self.ctx)
        self.phase = 'gen'
        self.R['schemes'][self.key] = {'summary': 'running', 'confirm': self.confirm}
        self.line('INFO', 'scheme %s (%d) pass started: runs %s' % (self.key, self.scheme_id, [n for n, _ in AS50P.plan(self.ctx)]))
        self.resume(None)

    # ---- the protocol generator
    def resume(self, value, throw=None):
        while True:
            try:
                if throw is not None:
                    item = self.gen.throw(throw)
                    throw = None
                else:
                    item = self.gen.send(value)
            except StopIteration as e:
                self.scheme_done(e.value, None)
                return
            except AS50P.SchemeAbort as e:
                self.line('FAIL', 'scheme %s aborted: %s' % (self.key, e))
                self.scheme_done(getattr(self.ctx, 'frags', {}), 'abort: %s' % e)
                return
            except Exception:  # noqa: BLE001
                self.err('protocol')
                self.scheme_done(getattr(self.ctx, 'frags', {}), 'protocol crash: %s' % traceback.format_exc().strip().splitlines()[-1])
                return
            if isinstance(item, AS50P.Frame):
                self.apply_frame(item)
                return
            if isinstance(item, AS50P.Reset):
                self.start_reset(item)
                return
            if isinstance(item, AS50P.Media):
                self.do_media(item)
            value = None

    def do_media(self, m):
        try:
            if m.what == 'chase_on':
                self.chase_on(m.label)
            elif m.what == 'chase_off':
                self.chase_off()
            elif m.what == 'still':
                if self.cfg['capture'] and (not self.listen or self.cfg.get('listen_captures')):
                    self.still(m.label)
            elif m.what == 'gate':
                self.gate_color(m.label, m.data)
        except Exception:  # noqa: BLE001
            self.err('media')

    def apply_frame(self, item):
        self.last_item = item
        if item.debug is not None:
            try:
                if item.debug == 'clear':
                    self.ship_p.debug_clear_input()
                else:
                    self.ship_p.debug_set_input(*item.debug)
            except Exception:  # noqa: BLE001
                self.err('debug_input')
            return
        raw = item.raw
        if raw.cam_yaw is not None or raw.cam_pitch is not None:
            cur = self.pc.get_control_rotation()
            self.set_cam(raw.cam_yaw if raw.cam_yaw is not None else cur.yaw, raw.cam_pitch if raw.cam_pitch is not None else wrap180(cur.pitch))
        if raw.throttle:
            self.inject('IA_AirshipThrottle', raw.throttle)
        if raw.steer:
            self.inject('IA_AirshipSteer', raw.steer)
        if raw.lift:
            self.inject('IA_AirshipLift', raw.lift)
        if raw.strafe:
            self.inject('IA_AirshipStrafe', raw.strafe)
        if raw.boost:
            self.inject('IA_AirshipBoost', 1.0)
        if raw.brake:
            self.inject('IA_AirshipBrake', 1.0)
        if raw.aim:
            self.inject('IA_AirshipAim', 1.0)
        if raw.zoom:
            self.inject('IA_AirshipZoom', raw.zoom)
        # Fire is bound on Started: press on alternate frames while the bot wants to fire (a release between presses)
        if raw.fire and not self.fire_prev:
            self.inject('IA_AirshipFire', 1.0)
            self.fire_prev = True
        else:
            self.fire_prev = False
        # Classic / Galleon / Sky Racer: a look input stamps LastLookInputTime (no recentre against the set camera);
        # Point & Fly: never (a set without look input is the absolute heading set, SCHEME_POINTFLY.md 13)
        if raw.look and self.key != 'pointfly':
            self.inject('IA_AirshipLook', 0.01, 0.0)

    # ---- the start pose of a run
    def area_loc(self, item):
        ox, oy = AS50_AREAS_CM[item.area]
        return (ox + item.offset_m[0] * 100.0, oy + item.offset_m[1] * 100.0, AS50_GROUND_TOP + item.agl_m * 100.0)

    def teleport(self, loc, yaw):
        self.ship_s.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
        self.zero_vel()

    def zero_vel(self):
        try:
            self.hull_s.set_physics_linear_velocity(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
            self.hull_s.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        except Exception:  # noqa: BLE001
            self.err('zero_vel')

    def start_reset(self, item):
        if self.run_name is not None:
            self.flush_run()
        self.chase_off()
        self.run_idx += 1
        self.run_name = item.run
        self.run_frames = 0
        self.run_wall0 = time.time()
        self.run_game0 = self.now
        self.fire_prev = False
        self.last_item = None
        try:
            self.ship_p.debug_clear_input()
        except Exception:  # noqa: BLE001
            pass
        if not self.possessed():
            self.line('WARN', 'the pilot does not possess the ship: boarding again')
            self.cmd(self.sw, 'Aura.Airship.Board %d' % (1 if self.listen else 0))
        loc = self.area_loc(item)
        self.teleport(loc, item.yaw_deg)
        self.set_cam(item.yaw_deg, self.ctx.PP['CameraDefaultPitch'])
        self.inject('IA_AirshipBrake', 1.0)        # a brake press re-latches the altitude hold at the new height
        # The scheme is re-applied 2 frames later (reset_tick), once the teleport and the zeroed velocity have gone
        # through a physics step (Galleon: GalleonNotch = NotchForSpeed of the hull's forward speed; the pre-build
        # review made ResetSchemePilotState read the live hull velocity, the wait is kept as a margin)
        self.reset_state = {'f': 0, 'loc': loc, 'yaw': item.yaw_deg}
        self.line('INFO', 'run %s: start pose %s cm, yaw %.0f (%s)' % (item.run, r(list(loc), 0), item.yaw_deg, item.area))

    def reset_tick(self, rec):
        st = self.reset_state
        st['f'] += 1
        f = st['f']
        if f <= 4:
            self.zero_vel()
        self.set_cam(st['yaw'], self.ctx.PP['CameraDefaultPitch'])
        if self.listen:
            # a client gets OnRep only on a change: bounce through another scheme, back once the client copy is at rest
            if f == 2:
                self.cmd(self.sw, 'Aura.Airship.Scheme %d' % ((self.scheme_id + 1) % 4))
            if f == 17:
                self.cmd(self.sw, 'Aura.Airship.Scheme %d' % self.scheme_id)
            if f in (30, 60):
                self.inject('IA_AirshipBrake', 1.0)
            min_f = 66
        else:
            if f == 2:
                self.cmd(self.sw, 'Aura.Airship.Scheme %d' % self.scheme_id)     # re-apply: scheme-local state reset
            if f == 30:
                self.inject('IA_AirshipBrake', 1.0)
            min_f = 36
        if f >= min_f:
            pv = rec['pilot']['view']
            rest = (abs(rec.get('SpeedMS', 9.0)) < 0.3 and abs(rec.get('VerticalSpeedMS', 9.0)) < 0.2 and abs(rec.get('RollDeg', 9.0)) < 1.5
                    and abs(rec.get('PitchDeg', 9.0)) < 2.0 and abs(rec.get('YawRateDegS', 9.0)) < 1.0 and abs(pv.get('SpeedMS', 9.0)) < 0.5)
            if rest or f >= min_f + 90:
                if not rest:
                    self.ctx.notes.setdefault(self.run_name, {'k0': {}, 'warn': []})['warn'].append(
                        'start pose not at rest after %.1f s: speed %.2f m/s, vz %.2f, roll %.1f, pitch %.1f, yaw rate %.1f' % (
                            f / FIXED_FPS, rec.get('SpeedMS', -1), rec.get('VerticalSpeedMS', -1), rec.get('RollDeg', -1),
                            rec.get('PitchDeg', -1), rec.get('YawRateDegS', -1)))
                d = dist(v3(self.ship_s.get_actor_location()), st['loc']) / 100.0
                if d > 2.0:
                    self.line('WARN', 'start pose drifted %.1f m during the reset' % d)
                return True
        return False

    def tick_gen(self):
        rec = self.read_record()
        if rec.get('bIsDead'):
            self.finish('the ship died (bIsDead): the test cannot go on')
            return
        if self.reset_state is not None:
            self.log_frame(rec, None, 'reset')
            if not self.reset_tick(rec):
                return
            self.reset_state = None
            self.ctx.begin_run(self.run_name)
            self.ctx.update(rec, advance=False)
            self.resume(rec)
            return
        self.ctx.update(rec)
        self.log_frame(rec, self.last_item)
        self.run_frames += 1
        if self.chase is not None:
            self.chase_frame()
        lim = AS50P.run_max_s(self.run_name) * FIXED_FPS
        wall_lim = 300.0 + 20.0 * AS50P.nominal_s(self.run_name)
        if self.run_frames > lim or time.time() - self.run_wall0 > wall_lim:
            self.line('FAIL', 'run %s timed out (%d frames, %.0f s wall)' % (self.run_name, self.run_frames, time.time() - self.run_wall0))
            self.resume(None, throw=AS50P.RunTimeout('run %s exceeded %.0f game s / %.0f wall s' % (self.run_name, lim / FIXED_FPS, wall_lim)))
            return
        self.resume(rec)

    # ---- one scheme done: metrics.json, telemetry.json, compare.md
    def load_metrics(self, key):
        try:
            with open(os.path.join(AS50_CTRL, key, 'metrics.json')) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def write_scheme(self, frags, error):
        key = self.key
        if key is None:
            return
        old = self.load_metrics(key)
        if self.listen:
            out, extra = AS50P.assemble(key, frags, base=dict((k, v) for k, v in (old or {}).items() if k != 'meta') or None)
            meta = dict((old or {}).get('meta') or {})
        else:
            out, extra = AS50P.assemble(key, frags)
            if old and ((old.get('meta') or {}).get('listen_pass')):      # keep a listen pass's lat100 values
                for m in ('M10', 'M11', 'M12'):
                    for path, v in AS50P.flat(old.get(m) or {}):
                        if 'lat100' in path.split('.'):
                            AS50P.put(out[m], path, v)
            meta = {}
        notes = self.ctx.notes if self.ctx else {}
        runs = {}
        for n, nt in notes.items():
            st = dict(self.run_stats.get(n, {}))
            st.update({'status': nt.get('status', 'not run'), 'k0': nt.get('k0'), 'warn': nt.get('warn')})
            if nt.get('gates'):
                st['gates'] = nt['gates']
            if nt.get('trace'):
                st['trace'] = nt['trace']
            runs[n] = st
        pass_meta = {'harness': AS50_VERSION, 'protocol': AS50P.PROTOCOL_VERSION, 'generated': time.strftime('%Y-%m-%d %H:%M'),
                     'net': 'listen (client pilot, Net PktLag %s ms)' % (self.R.get('pktlag') or {}).get('pktlag_ms') if self.listen else 'standalone',
                     'runtime_game_s': round(self.now - self.scheme_game0, 1), 'runtime_wall_s': round(time.time() - self.scheme_wall0, 1),
                     'runs': runs, 'scheme_confirm': self.confirm, 'error': error,
                     'telemetry_missing': sorted((self.ctx.missing if self.ctx else {}).keys()), 'hull_hits': self.hull_hits,
                     'media': dict((k, (v if isinstance(v, str) else ', '.join(v))) for k, v in self.media.items()),
                     'shared': dict((k, v) for k, v in ((self.ctx.shared if self.ctx else {}) or {}).items() if k in ('top', 'final_rate')),
                     'wind_note': 'PIE wind phase = GetUniqueID() % 97; the bench uses seed 1 (M1-M10), 7 (M11), 3 (M12)'}
        try:
            lines = self.log_since('scheme_' + key)
            pass_meta['inertia_log'] = [l.split('LogAirship', 1)[-1][:300] for l in lines if ('nertia' in l or 'MassSpace' in l or 'COM' in l)][:8]
            pass_meta['scheme_log'] = [l[:300] for l in lines if 'Aura.Airship.Scheme' in l][:6]
            pass_meta['log_errors'] = len([l for l in lines if 'Error:' in l or 'Ensure condition failed' in l])
        except Exception:  # noqa: BLE001
            self.err('scheme_log')
        if any(k.startswith('xcheck') for k in extra):
            pass_meta['xcheck'] = dict((k[len('xcheck.'):], v) for k, v in extra.items() if k.startswith('xcheck.'))
        reps = {}
        for k, v in extra.items():
            if k.startswith('repeat.'):
                _, rn, mk = k.split('.', 2)
                reps.setdefault(rn, {})[mk] = v
        if reps:
            pass_meta['repeats'] = reps
        if self.listen:
            meta['listen_pass'] = pass_meta
            meta['lat_measured'] = ['lat0', 'lat100'] if meta.get('source') == 'pie' else ['lat100']
            meta.setdefault('scheme', key)
            meta.setdefault('scheme_enum', self.scheme_id)
            meta.setdefault('label', AS50P.SCHEMES[self.scheme_id][1])
            meta.setdefault('source', 'pie')
        else:
            meta = dict(scheme=key, scheme_enum=self.scheme_id, label=AS50P.SCHEMES[self.scheme_id][1], source='pie',
                        fps=int(FIXED_FPS), start_agl_m=AS50P.START_AGL_M, course_agl_m=AS50P.COURSE_AGL_M, lat_measured=['lat0'],
                        **pass_meta)
            if old and (old.get('meta') or {}).get('listen_pass'):
                meta['listen_pass'] = old['meta']['listen_pass']
                meta['lat_measured'] = ['lat0', 'lat100']
        out = dict([('meta', meta)] + [('M%d' % i, out.get('M%d' % i, {})) for i in range(1, 13)])
        try:
            with open(os.path.join(self.sdir(key), 'metrics.json'), 'w') as f:
                json.dump(out, f, indent=1, default=str)
        except Exception:  # noqa: BLE001
            self.err('write_metrics')
        tj = self.combine_telemetry(key)
        n_ok = sum(1 for v in runs.values() if v.get('status') == 'ok')
        self.R['schemes'][key] = {'summary': '%s: %d/%d runs ok%s' % ('done' if not error else error[:120], n_ok, len(runs),
                                                                   '' if not pass_meta['telemetry_missing'] else ', missing telemetry %s' % pass_meta['telemetry_missing']),
                                  'confirm': self.confirm, 'metrics': os.path.join(AS50_CTRL, key, 'metrics.json'), 'telemetry': tj}
        try:
            AS50P.write_compare(AS50_CTRL)
        except Exception:  # noqa: BLE001
            self.err('compare_md')
        self.line('INFO', 'scheme %s written: %s' % (key, self.R['schemes'][key]['summary']))

    def scheme_done(self, frags, error):
        try:
            self.flush_run()
            self.chase_off()
            try:
                self.ship_p.debug_clear_input()
            except Exception:  # noqa: BLE001
                pass
            self.write_scheme(frags or {}, error)
        except Exception:  # noqa: BLE001
            self.err('scheme_done')
        self.ctx = None
        self.gen = None
        self.reset_state = None
        self.run_name = None
        self.next_scheme()

    # ---- the end: back to Classic, the exactness check (IMPLEMENTATION_PLAN.md 7)
    def tick_final(self):
        D = self.D
        D['f'] += 1
        f = D['f']
        if f == 1:
            self.cmd(self.sw, 'Aura.Airship.Scheme 0')
        if f == 15:
            self.log_mark('scheme_check')
            self.cmd(self.sw, 'Aura.Airship.Scheme check')
        if f == 20:
            self.cmd(self.sw, 'Aura.Airship.Scheme')
        if f >= 60:
            self.finish('all schemes done')


AS50_CFG_USED = dict(AS50_DEFAULTS)
AS50_CFG_USED.update(globals().pop('AS50_CFG', None) or {})    # consumed: the inbox namespace outlives this run
AS50_STOP = False
if 'AS50_RUN' in globals() and AS50_RUN is not None and AS50_RUN.phase not in ('finished',):
    print('FAIL: an as_50 run is active (phase %s): not armed again (stop it with as_50x_stop.py)' % AS50_RUN.phase)
else:
    AS50_RUN = As50Run(AS50_CFG_USED)
    if not AS50_RUN.arm():
        AS50_RUN.restore()
        AS50_RUN.remove_temp()
        AS50_RUN.phase = 'finished'
        print('\n'.join(AS50_RUN.R['lines']))
    else:
        print('armed %s: schemes %s, net %s, sloppy repeats %s, captures %s; status: cat %s' % (
            AS50_VERSION, AS50_CFG_USED['schemes'], AS50_CFG_USED['net'], AS50_CFG_USED['sloppy_repeats'], AS50_CFG_USED['capture'],
            os.path.join(AS50_CTRL, 'status.txt')))
