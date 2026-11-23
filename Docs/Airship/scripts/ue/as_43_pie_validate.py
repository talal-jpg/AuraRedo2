# as_43_pie_validate.py - validation PIE run of the drivable airship after the C++ fix rounds 2-3 and the validation
# asset changes (as_41 FX materials, as_42 M_Airship usage + PM_AirshipHull, as_12 V1/V2 wreck kick + CCD).
# Standalone, 1 player, fixed 30 fps game time (works with the editor window hidden), on L_AirshipTest.
# Built on as_30_pie_smoke.py (its AsRun class is exec'd without its auto-arm block and subclassed here), so the smoke
# checks a..k keep their exact criteria; new checks:
#   b2/b3/b4  ship HUD on screen + on-foot overlay collapsed while flying; both back after Exit and after death
#   a3        deck passenger stands 10 s: ship drift / sink / pitch (first smoke: ~18 cm/s down, +2..7 deg); since
#             2026-11-23 (F-D) the hull is put at rest at its start (AS43_A3_AT_REST; False: as the deck phases left it)
#   a4        deck passenger walks a 4-leg square on the deck (AddMovementInput, half speed): stays aboard, ship still
#   f2        boost + brake path: no launch (first smoke: clipped AS_Obstacle_1 at 86 m/s -> +27 m/s up, climbed to 97 m)
#   d1        head-on into the port cannon wall at full throttle: rebound, no upward launch, damage from the impact speed
#   d2        top-edge clip of the port cannon wall at boost speed: no upward launch
#   c2        thruster jets out at once at death, fan wash out within 3 s
#   j3        wreck: break-off parts' world distance from the hull after the crash, nothing under the ground, hull bounce
# Since 2026-11-23 (follow-up F-D + Fix2; thresholds unchanged, Classic C++ untouched) the run is independent of the
# build and of the deck phases. v1 seeds its wind sway per ship by GetUniqueID() % 97, which moves with every build,
# and has no station keeping, so the unpiloted hull's drift in the deck phases (a3) and where f2 meets AS_Obstacle_1
# changed from build to build; no check measures gusts. So the run's ship has its wind sway off for the whole run
# (AS43_WIND_OFF, restored in finish()), and the flight path (lift..brake: c_lift, d_throttle, e_steer, f_boost_brake,
# f2) starts from the ship's spawn x/y and yaw, level and at rest (AS43_PATH_FROM_SPAWN). Classic: 24/25 on every run,
# f2 +5.35 m/s against 5.0 m/s, a v1 limit (Docs/Airship/controls/PIE_RESULTS.md "Follow-up", "Fix2"). The AS43_*
# knobs are read from the inbox globals, which last for the editor session: a wrapper that changes one must reset it.
# The X window of the editor is grabbed for the HUD (Saved/Airship/val/xgrab/<label>.req -> a bash loop run by the
# caller: Docs/Airship/scripts/harness/xgrab_loop.sh; read-only X calls, no input). Scene captures (TEMP_AS_Capture as in
# as_30) -> Saved/Airship/captures/val/. Results: Saved/Airship/val/val_result.json, val_report.txt, val_log.txt.
# Run (map open, no PIE): inbox.sh 43 Docs/Airship/scripts/ue/as_43_pie_validate.py 120; status: inbox.sh 31 as_31_pie_status.py
import json, math, os, time, traceback  # unreal = inbox namespace

AS43_AS30 = '/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_30_pie_smoke.py'
_as43_src = open(AS43_AS30).read()
exec(compile(_as43_src[:_as43_src.index("\nif 'AS30_RUN' in globals()")], AS43_AS30, 'exec'), globals())

AS43_VERSION = 'as_43_pie_validate 2026-11-23'
VAL = os.path.join(OUT, 'val')
CAPS = os.path.join(OUT, 'captures', 'val')      # AsRun.capture writes here (global name)
XG = os.path.join(VAL, 'xgrab')
GROUND_TOP = -19950.0
DMG = 300.0                                       # 3 x 300 (the bumps cost health too)
KILL_LOC = (34684.0, -22273.0, 7933.0)            # where the first smoke test killed the ship (279 m above the ground top)
MAX_CAPS = 26
BREAKOFF = ['Thruster_FL', 'Thruster_FR', 'Thruster_RL', 'Thruster_RR', 'Turbine_L', 'Turbine_R', 'Rudder',
            'SearchLight_AftL', 'SearchLight_MidL', 'SearchLight_MidR', 'SearchLight_FwdC']
BUMPS = {   # teleport (cm, yaw deg), then input after 0.3 s (throttle, steer, lift, strafe, boost, brake)
    'bump_head': {'loc': (0.0, 1500.0, 1600.0), 'yaw': -90.0, 'input': (1.0, 0.0, 0.0, 0.0, False, False),
                  'what': 'head-on into AS_CannonWall_Port (face y -9300, top z 3100) at full throttle, hull origin z 1600'},
    'bump_clip': {'loc': (0.0, 1500.0, 3550.0), 'yaw': -90.0, 'input': (1.0, 0.0, 0.0, 0.0, True, False),
                  'what': 'over AS_CannonWall_Port with the keel 0.9-1.5 m below its top (z 3100) at boost speed, hull origin z 3550'},
}
PHASES = [('settle', 3.0), ('board', 3.0), ('hover', 10.0), ('cannons', 9.0), ('exit', 3.0), ('deck_stand', 10.0),
          ('deck_walk', 8.0), ('board2', 2.0), ('lift', 11.0), ('throttle', 10.0), ('steer', 8.0), ('boost', 4.0),
          ('brake', 4.0), ('damage', 3.0), ('bump_head', 9.0), ('bump_clip', 9.0), ('kill', 16.0)]


def en(x):
    """enum -> its name ('COLLAPSED', 'QUERY_ONLY', 'MOVE_WALKING'), whatever str() gives in this build"""
    n = getattr(x, 'name', None)
    return n if isinstance(n, str) else str(x).split('.')[-1].split(':')[0].strip('<> ')


class AsVal(AsRun):
    def __init__(self):
        AsRun.__init__(self)
        self.R['version'] = AS43_VERSION
        self.R['val'] = {}
        self.xg = []

    # ------------------------------------------------------------ scheme (2026-11-23 polish)
    def start_settle(self):
        """The v1 validation runs on Classic (AS43_SCHEME, default 0): since the polish the pawn's default scheme is
        Point & Fly, and these checks are v1's. Applied 3 s before boarding (the settle phase)."""
        want = int(globals().get('AS43_SCHEME', 0) or 0)
        names = {0: 'CLASSIC', 1: 'GALLEON', 2: 'SKY_RACER', 3: 'POINT_FLY'}
        try:
            self.ship.set_control_scheme(getattr(unreal.AirshipControlScheme, names[want]))
            self.line('INFO', 'control scheme set to %s (AS43_SCHEME %d; the pawn default is Point & Fly)' % (names[want], want))
        except Exception:  # noqa: BLE001
            self.err('set_control_scheme')
            self.cmd('Aura.Airship.Scheme %d' % want)
        self.R.setdefault('setup', {})['scheme'] = names.get(want)
        self.spawn_pose = {'loc': self.ship_loc(), 'yaw': float(self.ship.get_actor_rotation().yaw)}
        self.R['setup']['spawn_pose'] = {'loc_m': r([x / 100.0 for x in self.spawn_pose['loc']], 3), 'yaw': r(self.spawn_pose['yaw'], 2)}
        self.wind_off()
        AsRun.start_settle(self)

    # ------------------------------------------------------------ run-wide harness settings (Fix2, 2026-11-23)
    WIND = ('WindLateralAccel', 'WindRollAccel', 'WindPitchAccel')

    def wind_off(self):
        """v1 (Classic) seeds its wind sway per ship by GetUniqueID() % 97 (AirshipFlightComponent.cpp), which moves with
        every build (seeds 51 / 56 / 57 in the 2026-11-22/23 runs), and v1 has no station keeping, so the unpiloted hull's
        drift in the deck phases, and with it where the flight path meets AS_Obstacle_1, changed from build to build. No
        check measures gusts: the run's ship has its wind sway off from the settle phase on (AS43_WIND_OFF, default True),
        restored in finish(). The flight component reads these UPROPERTYs every tick."""
        st = {'enabled': bool(globals().get('AS43_WIND_OFF', True)), 'before': {}, 'restored': None}
        if st['enabled']:
            try:
                fc = self.ship.get_editor_property('Flight')
                for n in self.WIND:
                    st['before'][n] = float(fc.get_editor_property(n))
                    # NEVER: no Pre/PostEditChange on a PIE component (that re-registers it and reruns the BP construction)
                    fc.set_editor_property(n, 0.0, unreal.PropertyAccessChangeNotifyMode.NEVER)
                st['now'] = [float(fc.get_editor_property(n)) for n in self.WIND]
            except Exception:  # noqa: BLE001
                self.err('wind_off')
        self.wind = st
        self.R.setdefault('setup', {})['wind'] = st
        self.line('INFO', 'wind sway for the run (AS43_WIND_OFF %s): %s -> %s' % (st['enabled'], st['before'], st.get('now')))

    def wind_restore(self):
        st = getattr(self, 'wind', None)
        if not st or not st['before'] or st.get('restored') is not None:
            return
        try:
            if self.ship is not None and valid(self.ship):
                fc = self.ship.get_editor_property('Flight')
                for n, v in st['before'].items():
                    fc.set_editor_property(n, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
                st['restored'] = [float(fc.get_editor_property(n)) for n in self.WIND]
            else:
                st['restored'] = 'ship gone'
        except Exception:  # noqa: BLE001
            st['restored'] = 'failed'
            self.err('wind_restore')
        self.line('INFO', 'wind sway restored %s' % (st['restored'],))

    def finish(self, reason):
        if self.phase != 'finished':
            self.wind_restore()
        AsRun.finish(self, reason)

    # ------------------------------------------------------------ flight path start (Fix2, 2026-11-23)
    def start_lift(self):
        """The flight path (lift -> throttle -> steer -> boost -> brake) starts from the ship's spawn x/y and yaw, level and
        at rest, at its current height (the altitude hold is kept). as_43's deck phases before it (as_30's cannons, exit
        and board2, plus a3 and a4) leave the unpiloted v1 hull 0-7 m off and moving at up to 0.4 m/s, and f2's clip on
        AS_Obstacle_1 depends on where the hull meets it (+4.83..+5.98 m/s up in the 2026-11-22/23 Classic runs). From
        here, with the wind off, every run is the same: f2 +5.35 m/s, a v1 limit (controls/PIE_RESULTS.md "Fix2"). The
        pilot is aboard; the bumps and the kill teleport the same way. AS43_PATH_FROM_SPAWN False: start where the deck
        phases left the ship."""
        p = getattr(self, 'spawn_pose', None)
        st = {'enabled': bool(globals().get('AS43_PATH_FROM_SPAWN', True)) and p is not None}
        try:
            loc = self.ship_loc()
            rot = self.ship.get_actor_rotation()
            v = self.hull().get_physics_linear_velocity()
            st['before'] = {'loc_m': r([x / 100.0 for x in loc], 3), 'pitch_roll_yaw': r([rot.pitch, rot.roll, rot.yaw], 2),
                            'v_ms': r([v.x / 100.0, v.y / 100.0, v.z / 100.0], 3)}
            if st['enabled']:
                self.teleport((p['loc'][0], p['loc'][1], loc[2]), p['yaw'])
                st['after_loc_m'] = r([x / 100.0 for x in self.ship_loc()], 3)
        except Exception:  # noqa: BLE001
            self.err('path_start')
        self.R.setdefault('setup', {})['path_start'] = st
        self.line('INFO', 'flight path start (AS43_PATH_FROM_SPAWN %s): before %s -> %s' % (st['enabled'], st.get('before'), st.get('after_loc_m')))
        AsRun.start_lift(self)

    # ------------------------------------------------------------ outputs (own files; as_30's results stay)
    def line(self, tag, msg):
        s = '%s: [%7.2f %s] %s' % (tag, self.now, self.phase, msg)
        self.R['lines'].append(s)
        print(s)
        try:
            with open(os.path.join(VAL, 'val_log.txt'), 'a') as f:
                f.write(s + '\n')
        except Exception:  # noqa: BLE001
            pass

    def write(self, force=False):
        if not force and time.time() - self.last_write < 2.0:
            return
        self.last_write = time.time()
        self.R['phase'] = self.phase
        self.R['game_t'] = r(self.now)
        self.R['wall_s'] = r(time.time() - self.wall0, 1)
        try:
            with open(os.path.join(VAL, 'val_result.json'), 'w') as f:
                json.dump(self.R, f, indent=1, default=str)
        except Exception:  # noqa: BLE001
            pass

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
        write_val_report(self.R)
        self.line('INFO', 'done; results in val/val_result.json / val/val_report.txt')

    # ------------------------------------------------------------ helpers
    def xgrab(self, label):
        try:
            os.makedirs(XG, exist_ok=True)
            with open(os.path.join(XG, label + '.req'), 'w') as f:
                f.write(XG + '\n')
            self.xg.append({'label': label, 't': r(self.now), 'phase': self.phase})
            self.line('INFO', 'X grab requested: %s' % label)
        except Exception:  # noqa: BLE001
            self.err('xgrab')

    def capture(self, label, kind):
        if self.cap_dead or self.ncap >= MAX_CAPS:
            return None
        if kind != 'deck':
            n0 = self.ncap
            self.ncap = min(self.ncap, 13)          # as_30's limit is 14: let it through, count here
            res = AsRun.capture(self, label, kind)
            self.ncap = n0 + (1 if res else 0)
            return res
        try:
            if self.cap is None:
                n0 = self.ncap
                self.ncap = min(self.ncap, 13)
                AsRun.capture(self, '_init', 'none')     # builds self.cap (returns None for the unknown kind)
                self.ncap = n0
                if self.cap is None:
                    return None
            a, cc, rt = self.cap
            c = v3(self.char.get_actor_location())
            fwd = v3(self.ship.get_actor_forward_vector())
            rgt = v3(self.ship.get_actor_right_vector())
            frm = [c[i] - fwd[i] * 900.0 - rgt[i] * 1300.0 + (900.0 if i == 2 else 0.0) for i in range(3)]
            rot = unreal.MathLibrary.find_look_at_rotation(unreal.Vector(*frm), unreal.Vector(*c))
            cc.set_editor_property('fov_angle', 60.0)
            a.set_actor_location_and_rotation(unreal.Vector(*frm), rot, False, True)
            cc.capture_scene()
            name = '%s_%s' % (label, kind)
            unreal.RenderingLibrary.export_render_target(self.w, rt, CAPS, name + '.png')
            self.ncap += 1
            self.R['shots'].append({'label': label, 'kind': kind, 't': r(self.now), 'file': os.path.join(CAPS, name + '.png')})
            self.line('INFO', 'capture %s' % name)
            return name
        except Exception:  # noqa: BLE001
            self.err('capture_deck')
            return None

    def hull(self):
        return self.ship.get_editor_property('HullCollision')

    def hud_state(self):
        # unreal.WidgetBlueprintLibrary is not exposed to Python in this build (run 1: AttributeError): walk the
        # UserWidget objects of the PIE world instead
        d = {}
        try:
            d['shown'] = bool(self.ship.is_ship_hud_shown()) if valid(self.ship) else None
        except Exception:  # noqa: BLE001
            self.err('hud_shown')
        try:
            ship_w, ov, tl = [], [], []
            for w in unreal.ObjectIterator(unreal.UserWidget):
                try:
                    pn = w.get_path_name()
                    if 'UEDPIE' not in pn and 'GameInstance' not in pn:
                        continue
                    cn = w.get_class().get_name()
                    inv = bool(w.is_in_viewport())
                    if 'AirshipHUD' in cn:
                        ship_w.append((w.get_name(), inv, en(w.get_visibility())))
                    elif 'Overlay' in cn and inv:
                        ov.append((cn, en(w.get_visibility()), inv))
                    if inv:
                        tl.append(cn)
                except Exception:  # noqa: BLE001
                    continue
            d['ship_widgets'] = ship_w
            d['overlay'] = ov
            d['viewport_widgets'] = tl
        except Exception:  # noqa: BLE001
            self.err('hud_iter')
        return d

    def hud_check(self, key, flying):
        h = self.hud_state()
        ov = h.get('overlay') or []
        ship_on = [w for w in (h.get('ship_widgets') or []) if w[1]]
        if flying:
            ok = h.get('shown') is True and len(ship_on) == 1 and bool(ov) and all(o[1] == 'COLLAPSED' for o in ov)
            want = 'ship HUD shown, 1 ship HUD widget in the viewport, on-foot overlay COLLAPSED'
        else:
            ok = not h.get('shown') and not ship_on and bool(ov) and all(o[1] != 'COLLAPSED' and o[2] for o in ov)
            want = 'no ship HUD in the viewport, on-foot overlay back (not COLLAPSED, in the viewport)'
        self.check(key, 'PASS' if ok else 'FAIL', '%s; got: IsShipHUDShown %s, ship HUD widgets (name, in viewport, '
                   'visibility) %s, on-foot overlay (class, visibility, in viewport) %s; pawn %s'
                   % (want, h.get('shown'), h.get('ship_widgets'), ov, self.pawn().get_class().get_name() if self.pawn() else None), h)
        return ok

    def fx_state(self):
        out = {}
        for c in ('ThrusterFX_FL', 'ThrusterFX_FR', 'ThrusterFX_RL', 'ThrusterFX_RR', 'TurbineFX_L', 'TurbineFX_R'):
            try:
                nc = self.ship.get_editor_property(c)
                out[c] = {'active': bool(nc.is_active()), 'auto': bool(nc.get_editor_property('auto_activate'))}
            except Exception:  # noqa: BLE001
                self.err('fx_state')
        return out

    def local(self, p):
        x = unreal.MathLibrary.inverse_transform_location(self.ship.get_actor_transform(), unreal.Vector(*p))
        return [float(x.x), float(x.y), float(x.z)]

    def char_info(self):
        cm = gp(self.char, 'character_movement', 'CharacterMovement')
        caps = gp(self.char, 'capsule_component', 'CapsuleComponent')
        cl = v3(self.char.get_actor_location())
        base = self.char.get_movement_base() if hasattr(self.char, 'get_movement_base') else None
        return {'loc': r(cl, 1), 'local': r(self.local(cl), 1),
                'mode': en(cm.get_editor_property('movement_mode')) if cm else None,
                'base': base.get_name() if base else None,
                'coll': en(caps.get_collision_enabled()) if caps else None,
                'rider': self.char.get_name() in [p.get_name() for p in self.ship.get_passengers()]}

    def sample(self, force=False):
        s = AsRun.sample(self, force)
        if s is not None and self.phase in ('deck_stand', 'deck_walk', 'exit'):
            try:
                s['char'] = self.char_info()
            except Exception:  # noqa: BLE001
                self.err('char_info')
        if s is not None and self.phase in ('bump_head', 'bump_clip', 'kill', 'boost', 'brake'):
            try:
                w = self.hull().get_physics_angular_velocity_in_degrees()
                s['w'] = r([w.x, w.y, w.z], 1)
            except Exception:  # noqa: BLE001
                self.err('angvel')
        return s

    def phase_series(self, ph):
        return [s for s in self.R['series'] if s.get('ph') == ph]

    # ------------------------------------------------------------ (b) HUD while flying / after exit
    def end_board(self):
        AsRun.end_board(self)
        self.hud_check('b2_hud_flying', True)
        self.xgrab('hud_flying')

    def end_hover(self):
        AsRun.end_hover(self)
        h = self.hud_state()
        self.R['val']['hud_end_hover'] = h

    def ph_exit(self, el):
        AsRun.ph_exit(self, el)
        if el >= 2.3 and 'xg' not in self.D:
            self.D['xg'] = True
            self.xgrab('hud_after_exit')

    def end_exit(self):
        AsRun.end_exit(self)
        self.hud_check('b3_hud_after_exit', False)

    # ------------------------------------------------------------ (a) deck passenger
    def a3_still_start(self):
        """Follow-up F-D (2026-11-23): a3 is about a player standing on the parked deck, not gusts. v1 (Classic) has no
        station keeping, so the unpiloted hull coasts on what the wind and the cannons phase left: 0.01-0.31 m/s at the
        a3 start in the 2026-11-22/23 runs (drift 0.82 / 3.1 / 2.3 m against the 1.5 m limit; the bench gives 2.3 m from
        0.31 m/s even with no wind). The wind sway is off for the whole run (wind_off, Fix2); here the hull is put at rest
        at the a3 start (velocities zeroed, no transform change: the passenger stays put). Thresholds unchanged."""
        st = {}
        try:
            fc = self.ship.get_editor_property('Flight')
            st['wind_now'] = [float(fc.get_editor_property(n)) for n in self.WIND]
        except Exception:  # noqa: BLE001
            self.err('a3_wind_read')
        st['at_rest'] = bool(globals().get('AS43_A3_AT_REST', True))
        try:
            h = self.hull()
            v = h.get_physics_linear_velocity()
            w = h.get_physics_angular_velocity_in_degrees()
            st['v_at_start_ms'] = r([v.x / 100.0, v.y / 100.0, v.z / 100.0], 3)
            st['w_at_start_degs'] = r([w.x, w.y, w.z], 2)
            rot = self.ship.get_actor_rotation()
            st['pitch_roll_at_start_deg'] = r([rot.pitch, rot.roll], 2)
            if st['at_rest']:
                h.set_physics_linear_velocity(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
                h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        except Exception:  # noqa: BLE001
            self.err('a3_at_rest')
        self.a3_still = st
        self.R.setdefault('setup', {})['a3_still'] = st
        self.line('INFO', 'a3 (F-D): wind sway now %s; hull velocity at the start %s m/s, %s deg/s (%s); pitch/roll %s deg' % (
            st.get('wind_now'), st.get('v_at_start_ms'), st.get('w_at_start_degs'),
            'zeroed' if st['at_rest'] else 'kept', st.get('pitch_roll_at_start_deg')))

    def start_deck_stand(self):
        self.ship.debug_clear_input()
        self.a3_still_start()
        self.D['loc0'] = self.ship_loc()
        self.D['t0'] = self.tele()
        self.D['c0'] = self.char_info()

    def ph_deck_stand(self, el):
        if el >= 5.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('deck_stand', 'deck')
            self.capture('deck_stand', 'side')

    def ship_still(self, ss, loc0):
        loc1 = self.ship_loc()
        dxy = math.hypot(loc1[0] - loc0[0], loc1[1] - loc0[1]) / 100.0
        dz = (loc1[2] - loc0[2]) / 100.0
        pit = [s['PitchDeg'] for s in ss]
        rol = [s['RollDeg'] for s in ss]
        vz = [s['VerticalSpeedMS'] for s in ss]
        return {'drift_xy_m': r(dxy, 3), 'dz_m': r(dz, 3), 'pitch': [r(min(pit), 2), r(max(pit), 2)],
                'roll': [r(min(rol), 2), r(max(rol), 2)], 'vz_max_abs': r(max(abs(x) for x in vz), 3),
                'alt': [r(min(s['AltitudeM'] for s in ss), 3), r(max(s['AltitudeM'] for s in ss), 3)]}

    def end_deck_stand(self):
        ss = self.phase_series('deck_stand')
        st = self.ship_still(ss, self.D['loc0'])
        ci = [s['char'] for s in ss if s.get('char')]
        relz = [c['local'][2] for c in ci]
        riders = all(c['rider'] for c in ci) if ci else False
        modes = sorted(set(c['mode'] for c in ci))
        ok = (abs(st['dz_m']) < 0.3 and st['drift_xy_m'] < 1.5 and max(abs(x) for x in st['pitch']) < 1.0 and
              max(abs(x) for x in st['roll']) < 1.0 and st['vz_max_abs'] < 0.2 and riders and relz and max(relz) - min(relz) < 10.0)
        a3s = getattr(self, 'a3_still', None) or {}
        self.check('a3_deck_stand', 'PASS' if ok else 'FAIL', 'character standing on the deck 10 s (first smoke test: ship sank '
                   '~18 cm/s, 7 m in 3 s at 30 fps, pitch +2..7 deg): ship moved %.3f m sideways, %+.3f m up, pitch %s deg, roll %s '
                   'deg, |vz| max %.3f m/s, altitude %s m; character hull-local z %s..%s cm, modes %s, rider all the time %s, '
                   'capsule %s; harness: wind sway %s, hull velocity at the start %s m/s %s, pitch/roll at the start %s deg' % (
                       st['drift_xy_m'], st['dz_m'], st['pitch'], st['roll'], st['vz_max_abs'], st['alt'],
                       r(min(relz), 1) if relz else None, r(max(relz), 1) if relz else None, modes, riders,
                       sorted(set(c['coll'] for c in ci)), a3s.get('wind_now'), a3s.get('v_at_start_ms'),
                       'zeroed' if a3s.get('at_rest') else 'kept', a3s.get('pitch_roll_at_start_deg')),
                   {'ship': st, 'char': ci[::5], 'harness': a3s})

    WALK = [(0.0, 1.5, 'fwd'), (1.5, 3.0, 'stbd'), (3.0, 4.5, 'aft'), (4.5, 6.0, 'port')]

    def start_deck_walk(self):
        self.D['loc0'] = self.ship_loc()
        cm = gp(self.char, 'character_movement', 'CharacterMovement')
        self.D['walk_speed'] = gp(cm, 'max_walk_speed', default=None) if cm else None
        self.D['legs'] = {}

    def ph_deck_walk(self, el):
        fwd = self.ship.get_actor_forward_vector()
        rgt = self.ship.get_actor_right_vector()
        for t0, t1, leg in self.WALK:
            if t0 <= el < t1:
                d = {'fwd': fwd, 'stbd': rgt, 'aft': fwd * -1.0, 'port': rgt * -1.0}[leg]
                d = unreal.Vector(d.x, d.y, 0.0)
                self.char.add_movement_input(d, 0.5, False)
                if leg not in self.D['legs']:
                    self.D['legs'][leg] = {'t': r(el), 'start': self.char_info()['local']}
        if el >= 3.0 and 'cap' not in self.D:
            self.D['cap'] = True
            self.capture('deck_walk', 'deck')

    def end_deck_walk(self):
        ss = self.phase_series('deck_walk')
        st = self.ship_still(ss, self.D['loc0'])
        ci = [s['char'] for s in ss if s.get('char')]
        loc = [c['local'] for c in ci]
        relz = [p[2] for p in loc]
        riders = all(c['rider'] for c in ci) if ci else False
        modes = sorted(set(c['mode'] for c in ci))
        span_x = max(p[0] for p in loc) - min(p[0] for p in loc) if loc else 0
        span_y = max(p[1] for p in loc) - min(p[1] for p in loc) if loc else 0
        end = self.char_info()
        ok = (abs(st['dz_m']) < 0.3 and max(abs(x) for x in st['pitch']) < 1.5 and max(abs(x) for x in st['roll']) < 1.5 and
              riders and span_x > 150.0 and span_y > 150.0 and end['rider'] and 'FALLING' not in (end['mode'] or ''))
        self.check('a4_deck_walk', 'PASS' if ok else 'FAIL', 'character walks a square on the deck (4 legs x 1.5 s, half input, '
                   'max walk speed %s): hull-local path spans %.0f x %.0f cm (x by y), z %s..%s cm, modes %s, rider all the time %s, '
                   'end %s; ship moved %.3f m sideways, %+.3f m up, pitch %s, roll %s deg, |vz| max %.3f m/s'
                   % (self.D.get('walk_speed'), span_x, span_y, r(min(relz), 1) if relz else None, r(max(relz), 1) if relz else None,
                      modes, riders, end, st['drift_xy_m'], st['dz_m'], st['pitch'], st['roll'], st['vz_max_abs']),
                   {'ship': st, 'legs': self.D['legs'], 'path': loc[::3], 'end': end})

    # ------------------------------------------------------------ (f2) boost / brake path: no launch
    def end_brake(self):
        AsRun.end_brake(self)
        ss = self.phase_series('boost') + self.phase_series('brake')
        if not ss:
            return
        vz = [s['VerticalSpeedMS'] for s in ss]
        alt = [s['AltitudeM'] for s in ss]
        hl = [s.get('Health') for s in ss]
        hit = next((i for i in range(1, len(ss)) if hl[i] is not None and hl[i - 1] is not None and hl[i] < hl[i - 1] - 0.5), None)
        if hit is None:
            ok = max(vz) < 5.0
            msg = 'no hull hit on this path; vz max %+.2f m/s, altitude %.1f..%.1f m' % (max(vz), min(alt), max(alt))
        else:
            pre = ss[hit - 1]
            ref = max(pre.get('HoldAltitudeM', pre['AltitudeM']), pre['AltitudeM'])
            vz_after = max(vz[hit:])
            rise = max(alt[hit:]) - ref
            ok = vz_after < 5.0 and rise < 8.0
            msg = ('hull hit at game t %.2f (%s; health %s -> %s, speed %.1f -> %.1f m/s); after it vz max %+.2f m/s (before %+.2f), '
                   'altitude peak %.1f m = %+.1f m over the altitude hold / height before the hit (%.1f m; the flight floor keeps 4 m '
                   'over the obstacle, a brake press re-latches the hold)' % (ss[hit]['t'], ss[hit]['ph'], hl[hit - 1], hl[hit],
                   pre['SpeedMS'], ss[hit]['SpeedMS'], vz_after, pre['VerticalSpeedMS'], max(alt[hit:]), rise, ref))
        self.check('f2_boost_path', 'PASS' if ok else 'FAIL', 'boost 4 s + brake 4 s on the as_30 path (first smoke test: clipped '
                   'AS_Obstacle_1 at 86 m/s -> +27 m/s up, climbed to ~97 m): %s; spin max %s deg/s'
                   % (msg, max((max(abs(x) for x in s['w']) for s in ss if s.get('w')), default=None)),
                   {'vz': vz[::3], 'alt': alt[::3], 'hit_index': hit})

    # ------------------------------------------------------------ damage (3 x DMG)
    def ph_damage(self, el):
        for i, at in enumerate((0.2, 1.0, 1.8)):
            if el >= at and 'd%d' % i not in self.D:
                self.D['d%d' % i] = True
                self.cmd('Aura.Airship.Damage %d' % int(DMG))
            if el >= at + 0.5 and 'r%d' % i not in self.D:
                self.D['r%d' % i] = True
                self.D['hs'].append(self.tele().get('Health'))

    def end_damage(self):
        hs = self.D['hs']
        h0 = self.D['h0'] or 0
        ok = len(hs) == 3 and abs(h0 - DMG - hs[0]) < 1 and abs(hs[0] - DMG - hs[1]) < 1 and abs(hs[1] - DMG - hs[2]) < 1
        self.check('j1_damage', 'PASS' if ok else 'FAIL', 'Aura.Airship.Damage %d x3: health %s -> %s (MaxHealth %s), alive %s'
                   % (DMG, self.D['h0'], hs, self.tele().get('MaxHealth'), not self.ship.is_airship_dead()), {'h0': self.D['h0'], 'hs': hs})

    # ------------------------------------------------------------ (d) bumps
    def teleport(self, loc, yaw):
        self.ship.set_actor_location_and_rotation(unreal.Vector(*loc), unreal.Rotator(0.0, 0.0, float(yaw)), False, True)
        h = self.hull()
        h.set_physics_linear_velocity(unreal.Vector(0.0, 0.0, 0.0), False, 'None')
        h.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False, 'None')

    def bump_start(self, key):
        cfg = BUMPS[key]
        self.teleport(cfg['loc'], cfg['yaw'])
        self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, True)     # brake edge: altitude hold re-latched here
        self.D['cfg'] = cfg
        self.D['h0'] = self.tele().get('Health')
        self.D['trk'] = []
        self.line('INFO', '%s: teleported to %s yaw %.0f, health %s (%s)' % (key, cfg['loc'], cfg['yaw'], self.D['h0'], cfg['what']))

    def bump_tick(self, key, el):
        cfg = self.D['cfg']
        if el >= 0.3 and 'go' not in self.D:
            self.D['go'] = True
            self.ship.debug_set_input(*cfg['input'])
        t = self.tele()
        w = self.hull().get_physics_angular_velocity_in_degrees()
        rec = {'el': r(el, 3), 'z': r(self.ship_loc()[2], 1), 'y': r(self.ship_loc()[1], 1), 'vz': r(t.get('VerticalSpeedMS', 0), 3),
               'fwd': r(t.get('ForwardSpeedMS', 0), 3), 'spd': r(t.get('SpeedMS', 0), 3), 'h': t.get('Health'),
               'pitch': r(t.get('PitchDeg', 0), 2), 'w': r(max(abs(w.x), abs(w.y), abs(w.z)), 1)}
        trk = self.D['trk']
        if 'contact' not in self.D and trk:
            prev = trk[-1]
            if (rec['h'] is not None and prev['h'] is not None and rec['h'] < prev['h'] - 0.5) or rec['spd'] < prev['spd'] - 4.0:
                self.D['contact'] = len(trk)
                self.line('INFO', '%s: contact at %.2f s: speed %.1f -> %.1f m/s, health %s -> %s' % (key, el, prev['spd'], rec['spd'], prev['h'], rec['h']))
        trk.append(rec)
        ci = self.D.get('contact')
        if ci is not None and 'cap' not in self.D and el >= trk[ci]['el'] + 0.25:
            self.D['cap'] = True
            self.capture(key, 'side')
        if ci is not None and 'stop' not in self.D and el >= trk[ci]['el'] + 2.5:
            self.D['stop'] = True
            self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, True)

    def bump_end(self, key):
        trk = self.D['trk']
        ci = self.D.get('contact')
        self.ship.debug_set_input(0.0, 0.0, 0.0, 0.0, False, False)
        if ci is None:
            self.check('d_' + key, 'FAIL', 'no contact detected (%s); last %s' % (self.D['cfg']['what'], trk[-1] if trk else None),
                       {'trk': trk[::3]})
            return
        pre = trk[max(0, ci - 1)]
        after = trk[ci:]
        vz_max = max(x['vz'] for x in after)
        z_rise = (max(x['z'] for x in after) - pre['z']) / 100.0
        h1 = min(x['h'] for x in after if x['h'] is not None)
        dmg = (self.D['h0'] or 0) - h1
        spd_after = after[min(len(after) - 1, 5)]['spd']
        w_max = max(x['w'] for x in after)
        expect = max(0.0, (pre['spd'] - 4.0) * 6.0)
        ok = vz_max < 5.0 and z_rise < 8.0 and 0.0 < dmg <= 500.0 and w_max < 120.0
        self.check('d_' + key, 'PASS' if ok else 'FAIL', '%s: hit at %.1f m/s (fwd %.1f, pitch %.1f deg); after the contact: vz max %+.2f '
                   'm/s, hull rose %.2f m, speed 0.17 s later %.1f m/s, spin max %.0f deg/s, damage %.0f (hull %s -> %.0f; %.0f would be '
                   '6 per m/s above 4 of the whole speed, the code takes the speed along the contact normal)'
                   % (self.D['cfg']['what'], pre['spd'], pre['fwd'], pre['pitch'], vz_max, z_rise, spd_after, w_max, dmg,
                      self.D['h0'], h1, expect), {'trk': trk[max(0, ci - 6):ci + 40], 'contact_index': ci})

    def start_bump_head(self):
        self.bump_start('bump_head')

    def ph_bump_head(self, el):
        self.bump_tick('bump_head', el)

    def end_bump_head(self):
        self.bump_end('bump_head')

    def start_bump_clip(self):
        self.bump_start('bump_clip')

    def ph_bump_clip(self, el):
        self.bump_tick('bump_clip', el)

    def end_bump_clip(self):
        self.bump_end('bump_clip')

    # ------------------------------------------------------------ kill (j2 as_30) + c2 FX + b4 HUD + j3 wreck
    def start_kill(self):
        self.ship.debug_clear_input()
        self.teleport(KILL_LOC, self.ship.get_actor_rotation().yaw)
        self.D['loc0'] = self.ship_loc()
        self.D['v0'] = v3(self.ship.get_velocity())
        self.D['track'] = []
        self.D['fine'] = []
        self.line('INFO', 'kill: teleported to %s (%.0f m above the ground top), Kill in 0.2 s' % (KILL_LOC, (KILL_LOC[2] - GROUND_TOP) / 100.0))

    def ph_kill(self, el):
        if 'killed' not in self.D:
            if el < 0.2:
                return
            self.D['killed'] = el
            self.D['loc0'] = self.ship_loc()
            try:   # each part's horizontal distance from the hull origin while it still sits on the ship
                hl0 = self.ship_loc()
                self.D['rest_dxy'] = dict((b, math.hypot(*[v3(self.mesh.get_socket_location(b))[i] - hl0[i] for i in (0, 1)]) / 100.0)
                                          for b in BREAKOFF)
            except Exception:  # noqa: BLE001
                self.err('rest_dxy')
            self.cmd('Aura.Airship.Kill')
        AsRun.ph_kill(self, el)
        z = self.ship_loc()[2]
        self.D['fine'].append((r(el, 3), r(z, 1), r(self.ship.get_velocity().z, 1)))
        if int(el * 5) != self.D.get('_ww'):
            self.D['_ww'] = int(el * 5)
            try:
                hl = self.ship_loc()
                rec = {'t': r(el, 2), 'hull': r(hl, 0)}
                for b in BREAKOFF:
                    p = v3(self.mesh.get_socket_location(b))
                    rec[b] = [r(math.hypot(p[0] - hl[0], p[1] - hl[1]) / 100.0, 1), r((p[2] - hl[2]) / 100.0, 1)]
                self.R['val'].setdefault('wreck_world', []).append(rec)
            except Exception:  # noqa: BLE001
                self.err('wreck_world')
        dt = self.D.get('dead_t')
        if dt is not None:
            for at, k in ((0.3, 'fx_0.3'), (3.0, 'fx_3.0')):
                if el >= dt + at and k not in self.D:
                    self.D[k] = self.fx_state()
        pt = self.D.get('pilot_t')
        if pt is not None:
            if el >= pt + 1.5 and 'hud' not in self.D:
                self.D['hud'] = True
                self.hud_check('b4_hud_after_death', False)
            if el >= pt + 2.0 and 'xg' not in self.D:
                self.D['xg'] = True
                self.xgrab('hud_after_death')

    def end_kill(self):
        AsRun.end_kill(self)
        # c2 FX at death
        f3 = self.D.get('fx_0.3') or {}
        f30 = self.D.get('fx_3.0') or {}
        thr_off = bool(f3) and all(not v['active'] for k, v in f3.items() if k.startswith('Thruster'))
        fan_off = bool(f30) and all(not v['active'] for k, v in f30.items() if k.startswith('Turbine'))
        auto_off = bool(f3) and all(not v['auto'] for v in f3.values())
        self.check('c2_fx_death', 'PASS' if (thr_off and fan_off and auto_off) else 'FAIL', 'thruster jets inactive 0.3 s after '
                   'death %s, fan wash inactive 3 s after %s, auto-activate cleared %s: %s / %s' % (thr_off, fan_off, auto_off, f3, f30),
                   {'fx_0.3': f3, 'fx_3.0': f30})
        # j3 wreck: world positions of the break-off parts vs the hull, ground, bounce
        hl = self.ship_loc()
        parts = {}
        for b in BREAKOFF:
            try:
                p = v3(self.mesh.get_socket_location(b))
                parts[b] = {'dxy_m': r(math.hypot(p[0] - hl[0], p[1] - hl[1]) / 100.0, 1), 'z_above_ground_m': r((p[2] - GROUND_TOP) / 100.0, 2)}
            except Exception:  # noqa: BLE001
                self.err('wreck_parts')
        fine = self.D['fine']
        kz = self.D.get('killed', 0)
        imp = None
        for i in range(1, len(fine)):
            if fine[i][0] > kz + 0.5 and fine[i - 1][2] < -1500.0 and fine[i][2] > fine[i - 1][2] + 1000.0:
                imp = i
                break
        bounce = None
        v_imp = None
        if imp is not None:
            z_imp = fine[imp][1]
            v_imp = fine[imp - 1][2]
            bounce = (max(f[1] for f in fine[imp:]) - z_imp) / 100.0
        # run 1 compared the raw distance from the hull origin; the posts sit 25-30 m from it on the ship already, so the
        # check is on the distance beyond each part's own place on the ship (rest_dxy, taken right before the Kill)
        rest = self.D.get('rest_dxy') or {}
        for b, v in parts.items():
            if b in rest:
                v['rest_dxy_m'] = r(rest[b], 1)
                v['beyond_rest_m'] = r(v['dxy_m'] - rest[b], 1)
        d = [v.get('beyond_rest_m', v['dxy_m']) for v in parts.values()]
        under = [b for b, v in parts.items() if v['z_above_ground_m'] < -1.0]
        ok = bool(d) and max(d) <= 45.0 and not under and (bounce is None or bounce < 3.0)
        self.check('j3_wreck', 'PASS' if ok else 'FAIL', 'fall from %.0f m above the ground: impact at %s m/s, hull bounce %s m '
                   '(first smoke: 12 m at 68 m/s); break-off parts at the end, horizontal distance beyond their place on the ship '
                   '(m): %s (want ~10-40, max <= 45; raw distance from the hull origin %s); parts under the ground top: %s; hull at %s'
                   % ((KILL_LOC[2] - GROUND_TOP) / 100.0, None if v_imp is None else r(-v_imp / 100.0, 1),
                      None if bounce is None else r(bounce, 2), dict((b, v.get('beyond_rest_m')) for b, v in parts.items()),
                      dict((b, v['dxy_m']) for b, v in parts.items()), under, r(hl, 0)),
                   {'parts': parts, 'impact_index': imp, 'fine': fine[::2]})


def write_val_report(R):
    try:
        L = ['Airship validation PIE run (%s), armed %s, game time %.1f s, wall %.0f s, reason: %s' % (
            R.get('version'), R.get('armed_utc'), R.get('game_t', 0), R.get('wall_s', 0), R.get('reason'))]
        L.append('setup: %s' % R.get('setup'))
        for k in sorted(R['checks']):
            c = R['checks'][k]
            L.append('%s %s: %s' % (c['status'], k, c['summary']))
        L.append('script errors: %s' % dict((k, v['n']) for k, v in R['errors'].items()))
        for k, v in R['errors'].items():
            L.append('  %s: %s' % (k, v['last'].strip().splitlines()[-1] if v['last'] else ''))
        for k, v in (R.get('log_scan') or {}).items():
            L.append('log %s: %d' % (k, v['count']))
            for s in v['sample'][:10]:
                L.append('    %s' % s[:300])
        L.append('captures: %s' % [s['file'] for s in R['shots']])
        L.append('')
        L.append('telemetry (1 Hz): t phase | loc | speed fwd lat | alt hold | vz | yawrate roll pitch | throttle steer lift boost brake | health')
        last = -1
        for s in R['series']:
            if int(s['t']) == last:
                continue
            last = int(s['t'])
            L.append('%6.1f %-10s | %s | %s %s %s | %s %s | %s | %s %s %s | %s %s %s %s %s | %s' % (
                s['t'], s['ph'], s.get('loc'), s.get('SpeedMS'), s.get('ForwardSpeedMS'), s.get('LateralSpeedMS'),
                s.get('AltitudeM'), s.get('HoldAltitudeM'), s.get('VerticalSpeedMS'), s.get('YawRateDegS'), s.get('RollDeg'),
                s.get('PitchDeg'), s.get('Throttle'), s.get('Steer'), s.get('Lift'), s.get('Boost'), s.get('bBraking'), s.get('Health')))
        with open(os.path.join(VAL, 'val_report.txt'), 'w') as f:
            f.write('\n'.join(L) + '\n')
    except Exception:  # noqa: BLE001
        with open(os.path.join(VAL, 'val_report.txt'), 'w') as f:
            f.write('report failed: %s' % traceback.format_exc())


os.makedirs(VAL, exist_ok=True)
os.makedirs(CAPS, exist_ok=True)
if 'AS30_RUN' in globals() and AS30_RUN is not None and AS30_RUN.phase not in ('finished',):
    print('FAIL: a run is active (phase %s): not armed again' % AS30_RUN.phase)
else:
    AS43_RUN = AsVal()
    AS30_RUN = AS43_RUN               # as_31_pie_status.py / as_32_pie_stop.py read AS30_RUN
    if not AS43_RUN.arm():
        AS43_RUN.restore()
        AS43_RUN.remove_temp()
        AS43_RUN.phase = 'finished'
    else:
        print('armed %s' % AS43_VERSION)
