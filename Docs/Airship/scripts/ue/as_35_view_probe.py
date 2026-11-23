# as_35_view_probe.py - PIE look check: Standalone PIE, board at 2 s, throttle 0.6 + steer 0.4 from 3 s, writes
# Saved/Airship/view_probe.ready at 6 s (an X window grab of the editor's PIE viewport is taken from bash then:
# are the square particle sprites in the scene captures real?), fires the port broadside at 9 s, ready2 at 9.2 s,
# ends its own PIE at 12 s. Nothing saved.
import os, time  # unreal = inbox namespace
AS35_D = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), 'Airship')
for _f in ('view_probe.ready', 'view_probe.ready2', 'view_probe.done'):
    if os.path.exists(os.path.join(AS35_D, _f)):
        os.remove(os.path.join(AS35_D, _f))


class As35(object):
    def __init__(self):
        self.w = None; self.ship = None; self.t0 = None; self.done = set(); self.handle = None; self.wall = time.time()

    def at(self, t, k, fn):
        if self.now >= t and k not in self.done:
            self.done.add(k); fn()

    def mark(self, n):
        open(os.path.join(AS35_D, n), 'w').write('%.2f' % self.now)

    def tick(self, dt):
        try:
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if self.w is None:
                ws = list(unreal.EditorLevelLibrary.get_pie_worlds(False))
                if ws:
                    self.w = ws[0]
                elif time.time() - self.wall > 90:
                    self.end()
                return
            if not les.is_in_play_in_editor():
                self.end(); return
            tw = unreal.GameplayStatics.get_time_seconds(self.w)
            if self.ship is None:
                s = unreal.GameplayStatics.get_all_actors_of_class(self.w, unreal.load_class(None, '/Game/Assets/MyShip/Drivable/BP_AirshipPawn.BP_AirshipPawn_C'))
                if s:
                    self.ship, self.t0 = s[0], tw
                return
            self.now = tw - self.t0
            self.at(2.0, 'b', lambda: unreal.SystemLibrary.execute_console_command(self.w, 'Aura.Airship.Board'))
            self.at(3.0, 'i', lambda: self.ship.debug_set_input(0.6, 0.4, 0.0, 0.0, False, False))
            self.at(6.0, 'r', lambda: self.mark('view_probe.ready'))
            self.at(8.0, 'look', lambda: unreal.GameplayStatics.get_player_controller(self.w, 0).set_control_rotation(unreal.Rotator(0.0, -8.0, self.ship.get_actor_rotation().yaw - 90.0)))
            self.at(9.0, 'f', lambda: self.ship.request_fire())
            self.at(9.15, 'r2', lambda: self.mark('view_probe.ready2'))
            if self.now >= 12.0:
                self.end()
        except Exception as e:  # noqa: BLE001
            unreal.log_warning('as_35 %r' % e)

    def end(self):
        try:
            unreal.unregister_slate_post_tick_callback(self.handle)
        except Exception:  # noqa: BLE001
            pass
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if les.is_in_play_in_editor():
            les.editor_request_end_play()
        open(os.path.join(AS35_D, 'view_probe.done'), 'w').write('done')


if unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
    print('FAIL: PIE running')
else:
    AS35 = As35()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    AS35.handle = unreal.register_slate_post_tick_callback(AS35.tick)
    print('armed')
