# as_34_exit_probe.py - PIE experiment: after Aura.Airship.Exit the character stands on the deck and the hovering ship sank
# 7 m and pitched 13 deg nose-up in 3 s (smoke run 2). Which character-movement physics interaction does it?
# Standalone PIE on L_AirshipTest; game seconds: board at 2, exit at 5 (A: CMC defaults), board at 10, exit at 13 with
# B: bEnablePhysicsInteraction False on the character's CMC, board at 18, exit at 21 with C: interaction back on but
# StandingDownwardForceScale 0 / RepulsionForce 0 / PushForceFactor 0, end at 26. Samples ship z / pitch and the
# character's movement mode / base at 10 Hz into Saved/Airship/exit_probe.json. In-memory only; nothing saved.
import json, math, os, time, traceback  # unreal = inbox namespace

AS34_OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship', 'exit_probe.json')
AS34_SHIP = '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'


class As34(object):
    def __init__(self):
        self.R = {'samples': [], 'events': [], 'errors': []}
        self.w = None
        self.ship = None
        self.char = None
        self.t0 = None
        self.done = set()
        self.last = -1.0
        self.wall0 = time.time()
        self.handle = None

    def cmd(self, c):
        unreal.SystemLibrary.execute_console_command(self.w, c)
        self.R['events'].append([round(self.now, 2), c])

    def cmc(self, **kw):
        m = self.char.get_editor_property('character_movement')
        for k, v in kw.items():
            m.set_editor_property(k, v, unreal.PropertyAccessChangeNotifyMode.NEVER)
        self.R['events'].append([round(self.now, 2), 'cmc %s' % kw])

    def at(self, t, key, fn):
        if self.now >= t and key not in self.done:
            self.done.add(key)
            fn()

    def tick(self, dt):
        try:
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if self.w is None:
                ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
                if ws:
                    self.w = ws[0]
                elif time.time() - self.wall0 > 120:
                    self.end('no PIE')
                return
            if not les.is_in_play_in_editor():
                self.end('PIE ended')
                return
            tw = unreal.GameplayStatics.get_time_seconds(self.w)
            if self.ship is None:
                s = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, AS34_SHIP))
                pc = unreal.GameplayStatics.get_player_controller(self.w, 0)
                if s and pc and pc.get_controlled_pawn():
                    self.ship, self.char, self.t0 = s[0], pc.get_controlled_pawn(), tw
                    m = self.char.get_editor_property('character_movement')
                    self.R['cmc_defaults'] = dict((k, m.get_editor_property(k)) for k in (
                        'enable_physics_interaction', 'standing_downward_force_scale', 'repulsion_force', 'push_force_factor',
                        'initial_push_force_factor', 'mass'))
                return
            self.now = tw - self.t0
            self.at(2.0, 'b1', lambda: self.cmd('Aura.Airship.Board'))
            self.at(5.0, 'e1', lambda: self.cmd('Aura.Airship.Exit'))
            self.at(10.0, 'b2', lambda: self.cmd('Aura.Airship.Board'))
            self.at(12.9, 'pB', lambda: self.cmc(enable_physics_interaction=False))
            self.at(13.0, 'e2', lambda: self.cmd('Aura.Airship.Exit'))
            self.at(18.0, 'b3', lambda: self.cmd('Aura.Airship.Board'))
            self.at(20.9, 'pC', lambda: self.cmc(enable_physics_interaction=True, standing_downward_force_scale=0.0,
                                                 repulsion_force=0.0, push_force_factor=0.0, initial_push_force_factor=0.0))
            self.at(21.0, 'e3', lambda: self.cmd('Aura.Airship.Exit'))
            if self.now - self.last >= 0.1:
                self.last = self.now
                l = self.ship.get_actor_location()
                ro = self.ship.get_actor_rotation()
                cl = self.char.get_actor_location()
                m = self.char.get_editor_property('character_movement')
                try:
                    base = self.char.get_movement_base()
                    base = base.get_name() if base else None
                except Exception as e:  # noqa: BLE001
                    base = 'n/a %s' % e
                self.R['samples'].append([round(self.now, 2), round(l.z, 1), round(ro.pitch, 2), round(ro.roll, 2),
                                          round(cl.z - l.z, 1), str(m.get_editor_property('movement_mode')).split('.')[-1][:-4],
                                          base, bool(self.ship.has_pilot())])
            if self.now >= 26.0:
                self.end('done')
        except Exception:  # noqa: BLE001
            self.R['errors'].append(traceback.format_exc()[-600:])
            if len(self.R['errors']) > 30:
                self.end('errors')

    def end(self, why):
        self.R['why'] = why
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            les.editor_request_end_play()
        with open(AS34_OUT, 'w') as f:
            json.dump(self.R, f, indent=0, default=str)


if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
    print('FAIL: PIE running')
else:
    try:
        bcdo = unreal.get_default_object(unreal.load_class(None, '/Script/Aura.BurrowerSettings'))
        AS34_BURROWER = bool(bcdo.get_editor_property('bEnabled'))
        bcdo.set_editor_property('bEnabled', False, unreal.PropertyAccessChangeNotifyMode.NEVER)
    except Exception as _e:  # noqa: BLE001
        print('burrower setting: %r' % _e)
    AS34 = As34()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    AS34.handle = unreal.register_slate_post_tick_callback(AS34.tick)
    print('armed')
